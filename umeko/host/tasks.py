"""Durable, bounded machine tasks backed by the existing AgentService."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import mimetypes
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .identities import now, require_scope

TERMINAL = frozenset({"completed", "failed", "cancelled"})
MAX_FILE_BYTES = 20 * 1024 * 1024
logger = logging.getLogger(__name__)


def expiry(settings):
    return (datetime.now(timezone.utc) + timedelta(seconds=settings.task_retention_seconds)).isoformat()


class QueueFull(ValueError):
    pass


class IdempotencyConflict(ValueError):
    pass


def validate_input(payload: dict) -> tuple[dict, list[bytes]]:
    prompt = payload.get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 200_000:
        raise ValueError("prompt 须为非空文本，最多 200000 字符")
    model_id = payload.get("model_id")
    if model_id is not None and (not isinstance(model_id, str) or len(model_id) > 80):
        raise ValueError("model_id 无效")
    files = payload.get("files", [])
    if not isinstance(files, list) or len(files) > 10:
        raise ValueError("最多上传 10 个文件，总大小不超过 20 MiB")
    contents, file_views, total = [], [], 0
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("文件须包含 name 和 content_base64")
        name, encoded = item.get("name"), item.get("content_base64")
        if (not isinstance(name, str) or not 1 <= len(name) <= 200 or name in {".", ".."}
                or any(c in name for c in '/\\:\x00') or name.endswith((' ', '.')) or not isinstance(encoded, str)
                or len(encoded) > (MAX_FILE_BYTES * 4 // 3 + 4)):
            raise ValueError("文件名或 base64 内容无效，不能使用服务器路径")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("文件内容不是合法 base64") from exc
        total += len(content)
        if total > MAX_FILE_BYTES:
            raise ValueError("文件总大小不能超过 20 MiB")
        contents.append(content)
        file_views.append({"name": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    return {"prompt": prompt, "model_id": model_id, "files": file_views}, contents


class TaskService:
    def __init__(self, service, settings):
        self.service, self.store, self.settings = service, service.store, settings
        self.root = (service.data_root / "tasks").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._executor = None
        self._active: set[str] = set()
        self._lock = threading.Lock()
        with self.store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS service_tasks (
              id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              source TEXT NOT NULL, context_id TEXT NOT NULL, status TEXT NOT NULL,
              input_json TEXT NOT NULL, request_hash TEXT NOT NULL, idempotency_key TEXT,
              session_id TEXT, run_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              completed_at TEXT, expires_at TEXT NOT NULL, cancel_requested INTEGER NOT NULL DEFAULT 0,
              reply TEXT, error TEXT,
              UNIQUE(user_id, idempotency_key)
            );
            CREATE INDEX IF NOT EXISTS idx_service_tasks_owner ON service_tasks(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_service_tasks_status ON service_tasks(status, created_at);
            CREATE TABLE IF NOT EXISTS service_task_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_id TEXT NOT NULL REFERENCES service_tasks(id) ON DELETE CASCADE,
              type TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_task_events ON service_task_events(task_id, id);
            CREATE TABLE IF NOT EXISTS service_task_artifacts (
              id TEXT NOT NULL, task_id TEXT NOT NULL REFERENCES service_tasks(id) ON DELETE CASCADE,
              path TEXT NOT NULL, name TEXT NOT NULL, media_type TEXT NOT NULL, size INTEGER NOT NULL,
              PRIMARY KEY(task_id,id)
            );
            """)

    def start(self):
        if self._thread is not None:
            return
        self._stop.clear()
        # Single service process: never silently replay tools that may have side effects.
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            interrupted = db.execute("SELECT id FROM service_tasks WHERE status IN ('running','cancelling')").fetchall()
            db.execute("UPDATE service_tasks SET status='failed',error=?,completed_at=?,updated_at=?,expires_at=? "
                       "WHERE status IN ('running','cancelling')",
                       ("服务重启，任务执行已中断；请重新提交", now(), now(), expiry(self.settings)))
            for row in interrupted:
                self._event(db, row["id"], "task.failed", {"error": "服务重启，任务执行已中断；请重新提交"})
        self._executor = ThreadPoolExecutor(max_workers=self.settings.task_workers, thread_name_prefix="umeko-task")
        self._thread = threading.Thread(target=self._schedule, name="umeko-task-scheduler", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=True)
        self._thread = None

    def _directory(self, task_id: str) -> Path:
        candidate = (self.root / task_id).resolve()
        if candidate.parent != self.root or not task_id.startswith("task_"):
            raise ValueError("任务目录无效")
        return candidate

    def _remove_staging(self, task_id):
        candidate = self._directory(task_id)
        if candidate.exists():
            shutil.rmtree(candidate)

    def submit(self, principal: dict, payload: dict, *, source="rest", idempotency_key=None,
               context_id=None, message_id=None) -> dict:
        owner = require_scope(principal, "tasks:create")
        normalized, contents = validate_input(payload)
        if normalized["model_id"] and self.store.model_by_id(normalized["model_id"]) is None:
            raise ValueError("指定模型不存在")
        if idempotency_key is not None and (not isinstance(idempotency_key, str)
                                           or not 1 <= len(idempotency_key) <= 200):
            raise ValueError("幂等键须为 1–200 字符")
        if context_id is not None and (not isinstance(context_id, str) or len(context_id) > 100):
            raise ValueError("context_id 无效")
        fingerprint = hashlib.sha256(json.dumps({**normalized, "context_id": context_id},
                                                sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if message_id:
            normalized["message_id"] = message_id
        task_id, stamp = "task_" + uuid.uuid4().hex, now()
        expires = (datetime.now(timezone.utc) + timedelta(seconds=self.settings.task_retention_seconds)).isoformat()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                row = db.execute("SELECT * FROM service_tasks WHERE user_id=? AND idempotency_key=?",
                                 (owner, idempotency_key)).fetchone()
                if row:
                    if row["request_hash"] != fingerprint:
                        raise IdempotencyConflict("同一幂等键对应的输入不同")
                    return self._visible(self._view(db, row), principal)
            if context_id and db.execute("SELECT 1 FROM service_tasks WHERE context_id=? AND user_id=?",
                                         (context_id, owner)).fetchone() is None:
                raise KeyError("Context 不存在或无权访问")
            queued = db.execute("SELECT COUNT(*) FROM service_tasks WHERE status='queued'").fetchone()[0]
            owned = db.execute("SELECT COUNT(*) FROM service_tasks WHERE user_id=? "
                               "AND status NOT IN ('completed','failed','cancelled')", (owner,)).fetchone()[0]
            if queued >= self.settings.task_queue_limit or owned >= self.settings.task_caller_limit:
                raise QueueFull("任务队列已满，请稍后重试")
            directory = self._directory(task_id)
            try:
                directory.mkdir()
                for i, content in enumerate(contents):
                    (directory / str(i)).write_bytes(content)
                db.execute("INSERT INTO service_tasks(id,user_id,source,context_id,status,input_json,"
                           "request_hash,idempotency_key,created_at,updated_at,expires_at) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (task_id, owner, source, context_id or "ctx_" + uuid.uuid4().hex,
                            "queued", json.dumps(normalized, ensure_ascii=False), fingerprint, idempotency_key, stamp, stamp, expires))
                self._event(db, task_id, "task.queued", {})
            except BaseException:
                self._remove_staging(task_id)
                raise
            row = db.execute("SELECT * FROM service_tasks WHERE id=?", (task_id,)).fetchone()
            result = self._view(db, row)
        self._wake.set()
        return self._visible(result, principal)

    @staticmethod
    def _visible(result, principal):
        # Submission and cancellation do not grant permission to read an old result.
        if "tasks:read" not in principal.get("scopes", []):
            return {**result, "reply": None, "error": None, "artifacts": []}
        return result

    def _view(self, db, row) -> dict:
        return {**{key: row[key] for key in ("id", "context_id", "source", "status", "created_at", "updated_at",
                                           "completed_at", "expires_at", "reply", "error")},
                "expires_at": row["expires_at"] if row["status"] in TERMINAL else None,
                "artifacts": [dict(a) for a in db.execute("SELECT id,name,media_type,size FROM service_task_artifacts WHERE task_id=?", (row["id"],))]}

    def _owned(self, db, task_id, owner):
        row = db.execute("SELECT * FROM service_tasks WHERE id=? AND user_id=? "
                         "AND (expires_at>? OR status NOT IN ('completed','failed','cancelled'))",
                         (task_id, owner, now())).fetchone()
        if row is None:
            raise KeyError("任务不存在、已到期或无权访问")
        return row

    def get(self, principal, task_id) -> dict:
        owner = require_scope(principal, "tasks:read")
        with self.store.connect() as db:
            return self._view(db, self._owned(db, task_id, owner))

    def list(self, principal, *, limit=50, offset=0, context_id=None, status=None, updated_after=None) -> dict:
        owner = require_scope(principal, "tasks:read")
        where, args = "user_id=? AND (expires_at>? OR status NOT IN ('completed','failed','cancelled'))", [owner, now()]
        for field, value in [("context_id", context_id)]:
            if value:
                where += " AND " + field + "=?"
                args.append(value)
        if status is not None:
            states = [status] if isinstance(status, str) else list(status)
            if not states:
                return {"tasks": [], "total": 0}
            where += " AND status IN (" + ",".join("?" for _ in states) + ")"
            args.extend(states)
        if updated_after:
            where += " AND updated_at>?"
            args.append(updated_after)
        with self.store.connect() as db:
            total = db.execute("SELECT COUNT(*) FROM service_tasks WHERE " + where, args).fetchone()[0]
            rows = db.execute("SELECT * FROM service_tasks WHERE " + where + " ORDER BY created_at DESC LIMIT ? OFFSET ?",
                              [*args, min(max(limit, 1), 100), max(offset, 0)]).fetchall()
            return {"tasks": [self._view(db, r) for r in rows], "total": total}

    def cancel(self, principal, task_id) -> dict:
        owner = require_scope(principal, "tasks:cancel")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._owned(db, task_id, owner)
            if row["status"] not in TERMINAL:
                status = "cancelled" if row["status"] == "queued" else "cancelling"
                db.execute("UPDATE service_tasks SET cancel_requested=1,status=?,updated_at=?,completed_at=?,expires_at=? WHERE id=?",
                           (status, now(), now() if status == "cancelled" else None, expiry(self.settings), task_id))
                self._event(db, task_id, "task." + status, {})
            row = db.execute("SELECT * FROM service_tasks WHERE id=?", (task_id,)).fetchone()
            result = self._view(db, row)
        if result["status"] == "cancelled":
            self._remove_staging(task_id)
        self._wake.set()
        return self._visible(result, principal)

    def events(self, principal, task_id, after=0) -> list[dict]:
        owner = require_scope(principal, "tasks:read")
        with self.store.connect() as db:
            self._owned(db, task_id, owner)
            return [{**dict(r), "data": json.loads(r["data"])} for r in db.execute(
                "SELECT id,type,data,created_at FROM service_task_events WHERE task_id=? AND id>? ORDER BY id", (task_id, after))]

    @staticmethod
    def _event(db, task_id, kind, data):
        db.execute("INSERT INTO service_task_events(task_id,type,data,created_at) VALUES(?,?,?,?)",
                   (task_id, kind, json.dumps(data, ensure_ascii=False), now()))
        db.execute("DELETE FROM service_task_events WHERE task_id=? AND id NOT IN "
                   "(SELECT id FROM service_task_events WHERE task_id=? ORDER BY id DESC LIMIT 500)", (task_id, task_id))

    def artifact(self, principal, task_id, artifact_id) -> tuple[Path, str]:
        owner = require_scope(principal, "artifacts:read")
        with self.store.connect() as db:
            row = self._owned(db, task_id, owner)
            item = db.execute("SELECT * FROM service_task_artifacts WHERE task_id=? AND id=?", (task_id, artifact_id)).fetchone()
        if item is None or not row["session_id"]:
            raise KeyError("产物不存在")
        root = (self.service.data_root / "users" / owner / "sessions" / row["session_id"]).resolve()
        candidate = (root / item["path"]).resolve()
        if (not root.is_relative_to(self.service.data_root) or not candidate.is_relative_to(root)
                or candidate == root or not candidate.is_file()):
            raise KeyError("产物不存在")
        return candidate, item["media_type"]

    def _schedule(self):
        last_gc = 0.0
        while not self._stop.is_set():
            try:
                if time.monotonic() - last_gc > 60:
                    self.cleanup()
                    last_gc = time.monotonic()
                with self._lock:
                    available = self.settings.task_workers - len(self._active)
                if available:
                    with self.store.connect() as db:
                        db.execute("BEGIN IMMEDIATE")
                        rows = db.execute("SELECT id FROM service_tasks WHERE status='queued' ORDER BY created_at LIMIT ?",
                                          (available,)).fetchall()
                        for row in rows:
                            db.execute("UPDATE service_tasks SET status='running',updated_at=? WHERE id=?", (now(), row["id"]))
                    for row in rows:
                        with self._lock:
                            self._active.add(row["id"])
                        self._executor.submit(self._execute, row["id"])
            except Exception:
                logger.exception("Task scheduler error")
            self._wake.wait(0.25)
            self._wake.clear()

    def _execute(self, task_id):
        session, run = None, None
        try:
            with self.store.connect() as db:
                row = db.execute("SELECT * FROM service_tasks WHERE id=?", (task_id,)).fetchone()
                if row["cancel_requested"]:
                    db.execute("UPDATE service_tasks SET status='cancelled',completed_at=?,updated_at=?,expires_at=? WHERE id=?", (now(), now(), expiry(self.settings), task_id))
                    self._event(db, task_id, "task.cancelled", {})
                    return
            payload = json.loads(row["input_json"])
            session = self.service.create_session(user_id=row["user_id"], title="服务任务 " + task_id[-8:])
            with self.store.connect() as db:
                db.execute("UPDATE service_tasks SET session_id=? WHERE id=?", (session.id, task_id))
                db.execute("UPDATE agent_sessions SET purpose='task' WHERE id=?", (session.id,))
            if payload["model_id"]:
                self.store.set_session_model_override(session.id, payload["model_id"])
            attachments = [self.service.save_file(session.id, item["name"], (self._directory(task_id) / str(i)).read_bytes())[0]
                           for i, item in enumerate(payload["files"])]
            with self.store.connect() as db:
                if db.execute("SELECT cancel_requested FROM service_tasks WHERE id=?", (task_id,)).fetchone()[0]:
                    db.execute("UPDATE service_tasks SET status='cancelled',completed_at=?,updated_at=?,expires_at=? WHERE id=?", (now(), now(), expiry(self.settings), task_id))
                    self._event(db, task_id, "task.cancelled", {})
                    return
            run = self.service.create_run(session.id, payload["prompt"], attachments)
            with self.store.connect() as db:
                db.execute("UPDATE service_tasks SET session_id=?,run_id=? WHERE id=?", (session.id, run.id, task_id))
                self._event(db, task_id, "task.running", {})
            cursor, began = 0, time.monotonic()
            while True:
                with self.store.connect() as db:
                    cancellation = db.execute("SELECT cancel_requested FROM service_tasks WHERE id=?", (task_id,)).fetchone()[0]
                    if cancellation or self._stop.is_set() or time.monotonic() - began > self.settings.task_timeout_seconds:
                        run.request_cancel()
                    for event in run.events_after(cursor):
                        cursor = event["id"]
                        # Persist progress, without exposing absolute host paths or unbounded tool output.
                        data = self._public_data(session.id, event["data"])
                        if len(json.dumps(data)) > 16384:
                            data = {"summary": "事件内容超过 16 KiB，完整结果请读取任务产物"}
                        self._event(db, task_id, event["type"], data)
                if run.finished or self._stop.is_set():
                    break
                time.sleep(0.1)
            stamp = now()
            status = run.status if run.finished else "failed"
            reply = self.service.web_text(session.id, run.reply)
            error = self.service.web_text(session.id, run.error) if run.finished else "服务停止，任务执行已中断"
            with self.store.connect() as db:
                expires = (datetime.now(timezone.utc) + timedelta(seconds=self.settings.task_retention_seconds)).isoformat()
                db.execute("UPDATE service_tasks SET status=?,reply=?,error=?,updated_at=?,completed_at=?,expires_at=? WHERE id=?",
                           (status, reply, error, stamp, stamp, expires, task_id))
                for item in self.service.artifacts(session.id):
                    path = item["_path"].resolve()
                    relative = Path(item["name"])
                    if relative.parts[0] not in {"generate", "workspace"} or not path.is_relative_to(session.root.resolve()):
                        continue
                    db.execute("INSERT OR REPLACE INTO service_task_artifacts VALUES(?,?,?,?,?,?)",
                               (item["id"], task_id, item["name"], item["name"],
                                mimetypes.guess_type(path.name)[0] or "application/octet-stream", item["size"]))
                self._event(db, task_id, "task." + status, {"reply": reply, "error": error})
        except Exception as exc:
            error = self.service.web_text(session.id, str(exc)) if session else "任务初始化失败，请管理员检查配置"
            with self.store.connect() as db:
                db.execute("UPDATE service_tasks SET status='failed',error=?,completed_at=?,updated_at=?,expires_at=? WHERE id=?",
                           (error, now(), now(), expiry(self.settings), task_id))
                self._event(db, task_id, "task.failed", {"error": error})
            logger.exception("Machine task failed: %s", task_id)
        finally:
            if session and (run is None or run.finished):
                self.service.evict_session(session.id)
            if run and run.finished:
                self.service.run_manager.forget(run.id)
            try:
                self._remove_staging(task_id)
            except OSError:
                logger.exception("Failed to remove staging files: %s", task_id)
            finally:
                with self._lock:
                    self._active.discard(task_id)
                self._wake.set()

    def cleanup(self) -> int:
        with self.store.connect() as db:
            rows = db.execute("SELECT id,session_id FROM service_tasks WHERE expires_at<=? "
                              "AND status IN ('completed','failed','cancelled')", (now(),)).fetchall()
        count = 0
        for row in rows:
            with self._lock:
                if row["id"] in self._active:
                    continue
            if row["session_id"] and self.store.session_by_id(row["session_id"]):
                self.service.delete_session_admin(row["session_id"])
            self._remove_staging(row["id"])
            with self.store.connect() as db:
                db.execute("DELETE FROM service_tasks WHERE id=?", (row["id"],))
            count += 1
        return count

    def _public_data(self, session_id, value):
        if isinstance(value, str):
            return self.service.web_text(session_id, value)
        if isinstance(value, dict):
            return {key: self._public_data(session_id, item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._public_data(session_id, item) for item in value]
        return value

    def snapshot(self) -> dict:
        with self.store.connect() as db:
            counts = dict(db.execute("SELECT status,COUNT(*) FROM service_tasks GROUP BY status"))
        return {"counts": counts, "workers": self.settings.task_workers, "queue_limit": self.settings.task_queue_limit,
                "caller_limit": self.settings.task_caller_limit, "retention_seconds": self.settings.task_retention_seconds}
