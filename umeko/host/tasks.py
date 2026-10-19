"""Durable, bounded machine tasks backed by the existing AgentService."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import mimetypes
import os
import secrets
import shutil
import stat
import tempfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

from .identities import SCOPES, now, require_scope
from .file_manifest import ROOTS, _linked, session_root
from .results import validate_result, verify_result_files
from .task_input import TaskInputError, validate_prompt

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
    validate_prompt(prompt)
    if "model_id" in payload:
        raise ValueError("对外任务不支持选择 model_id，请使用管理员配置的默认模型")
    files = payload.get("files", [])
    if not isinstance(files, list) or len(files) > 10:
        raise TaskInputError("INVALID_FILES", "最多上传 10 个文件，总大小不超过 20 MiB。", "files")
    contents, file_views, total = [], [], 0
    for item in files:
        if not isinstance(item, dict):
            raise TaskInputError("INVALID_FILE", "文件须包含 name 和 content_base64。", "files")
        name, encoded = item.get("name"), item.get("content_base64")
        if (not isinstance(name, str) or not 1 <= len(name) <= 200 or name in {".", ".."}
                or any(c in name for c in '/\\:\x00') or name.endswith((' ', '.')) or not isinstance(encoded, str)
                or len(encoded) > (MAX_FILE_BYTES * 4 // 3 + 4)):
            raise TaskInputError("INVALID_FILE", "文件名或 base64 内容无效，不能使用服务器路径。", "files")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise TaskInputError("INVALID_FILE_ENCODING", "文件内容不是合法 base64；不要包含 data URL 头部。", "files") from exc
        total += len(content)
        if total > MAX_FILE_BYTES:
            raise TaskInputError("FILES_TOO_LARGE", "文件总大小不能超过 20 MiB。", "files")
        contents.append(content)
        file_views.append({"name": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    return {"prompt": prompt, "model_id": None, "files": file_views}, contents


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
              reply TEXT, error TEXT, caller_ip TEXT,
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
            CREATE TABLE IF NOT EXISTS service_task_file_refs (
              task_id TEXT NOT NULL REFERENCES service_tasks(id) ON DELETE CASCADE,
              file_id INTEGER NOT NULL, path TEXT NOT NULL, type TEXT NOT NULL,
              PRIMARY KEY(task_id,file_id), UNIQUE(task_id,path,type)
            );
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(service_tasks)")}
            if "caller_ip" not in columns:
                db.execute("ALTER TABLE service_tasks ADD COLUMN caller_ip TEXT")
            if "agent_id" not in columns:
                db.execute("ALTER TABLE service_tasks ADD COLUMN agent_id TEXT NOT NULL DEFAULT ''")
            if "request_key" not in columns:
                db.execute("ALTER TABLE service_tasks ADD COLUMN request_key TEXT")
                db.execute("UPDATE service_tasks SET request_key=idempotency_key")
            if "file_manifest_json" not in columns:
                db.execute("ALTER TABLE service_tasks ADD COLUMN file_manifest_json TEXT")
            if "result_json" not in columns:
                db.execute("ALTER TABLE service_tasks ADD COLUMN result_json TEXT")
            if "workspace_token" not in columns:
                db.execute("ALTER TABLE service_tasks ADD COLUMN workspace_token TEXT")
            for name in ("workspace_expires_at", "workspace_opened_at", "workspace_last_active_at", "workspace_evicted_at"):
                if name not in columns:
                    db.execute("ALTER TABLE service_tasks ADD COLUMN " + name + " TEXT")
            for row in db.execute("SELECT id FROM service_tasks WHERE workspace_token IS NULL").fetchall():
                db.execute("UPDATE service_tasks SET workspace_token=? WHERE id=?", (secrets.token_urlsafe(32), row["id"]))
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_task_workspace_token ON service_tasks(workspace_token)")
            db.execute("UPDATE service_tasks SET workspace_expires_at=? WHERE workspace_expires_at IS NULL "
                       "AND status IN ('completed','failed','cancelled')", (self.workspace_expiry(False),))
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_task_request_key ON service_tasks(user_id,agent_id,request_key)")

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
                db.execute("UPDATE service_tasks SET workspace_expires_at=? WHERE id=?", (self.workspace_expiry(False), row["id"]))
            for row in interrupted:
                self._event(db, row["id"], "task.failed", {"error": "服务重启，任务执行已中断；请重新提交"})
        self._executor = ThreadPoolExecutor(max_workers=self.settings.task_workers, thread_name_prefix="umeko-task")
        self._thread = threading.Thread(target=self._schedule, name="umeko-task-scheduler", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        for run in list(self.service.runs.values()):
            record = self.store.session_by_id(run.session_id)
            if record and record.get("purpose") == "task" and not run.finished:
                run.request_cancel()
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
               context_id=None, message_id=None, caller_ip=None) -> dict:
        owner = require_scope(principal, "tasks:create")
        agent_id = principal.get("agent_id", "")
        normalized, contents = validate_input(payload)
        if idempotency_key is not None and (not isinstance(idempotency_key, str)
                                           or not 1 <= len(idempotency_key) <= 200):
            raise ValueError("幂等键须为 1–200 字符")
        if context_id is not None and (not isinstance(context_id, str) or len(context_id) > 100):
            raise ValueError("context_id 无效")
        fingerprint = hashlib.sha256(json.dumps({**normalized, "context_id": context_id},
                                                sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        definition = principal.get("agent_definition")
        if agent_id:
            if not definition or definition["id"] != agent_id:
                raise ValueError("智能体配置无效")
            normalized["agent_snapshot"] = self.service.agent_registry.snapshot(definition)
            normalized["model_id"] = definition.get("default_model_id")
        if message_id:
            normalized["message_id"] = message_id
        task_id, stamp = "task_" + uuid.uuid4().hex, now()
        expires = (datetime.now(timezone.utc) + timedelta(seconds=self.settings.task_retention_seconds)).isoformat()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM users WHERE id=?", (owner,)).fetchone() is None:
                raise PermissionError("服务账号已删除")
            if agent_id and db.execute("SELECT 1 FROM agent_definitions WHERE id=? AND enabled=1", (agent_id,)).fetchone() is None:
                raise KeyError("智能体不存在或已停用")
            if idempotency_key:
                row = db.execute("SELECT * FROM service_tasks WHERE user_id=? AND agent_id=? AND request_key=?",
                                 (owner, agent_id, idempotency_key)).fetchone()
                if row:
                    if row["request_hash"] != fingerprint:
                        raise IdempotencyConflict("同一幂等键对应的输入不同")
                    return self._visible(self._view(db, row), principal)
            if context_id and db.execute("SELECT 1 FROM service_tasks WHERE context_id=? AND user_id=? AND agent_id=?",
                                         (context_id, owner, agent_id)).fetchone() is None:
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
                           "request_hash,request_key,created_at,updated_at,expires_at,caller_ip,agent_id,workspace_token) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (task_id, owner, source, context_id or "ctx_" + uuid.uuid4().hex,
                            "queued", json.dumps(normalized, ensure_ascii=False), fingerprint, idempotency_key, stamp, stamp, expires, caller_ip, agent_id, secrets.token_urlsafe(32)))
                self._event(db, task_id, "task.queued", {})
            except BaseException:
                self._remove_staging(task_id)
                raise
            row = db.execute("SELECT * FROM service_tasks WHERE id=?", (task_id,)).fetchone()
            result = self._view(db, row)
        self._wake.set()
        logger.info("Machine task submitted: id=%s agent_id=%s source=%s caller_id=%s caller_ip=%s", task_id, agent_id or "default", source, owner, caller_ip or "unknown")
        return self._visible(result, principal)

    @staticmethod
    def _visible(result, principal):
        result = {**result, "workspace_token": result.get("workspace_token") if SCOPES <= set(principal.get("scopes", [])) else None}
        # Submission and cancellation do not grant permission to read an old result.
        if "tasks:read" not in principal.get("scopes", []):
            return {**result, "reply": None, "error": None, "artifacts": []}
        return result

    def _view(self, db, row) -> dict:
        return {**{key: row[key] for key in ("id", "agent_id", "context_id", "source", "status", "created_at", "updated_at",
                                           "completed_at", "expires_at", "reply", "error")},
                "expires_at": row["expires_at"] if row["status"] in TERMINAL else None,
                "workspace_token": row["workspace_token"],
                "workspace_expires_at": row["workspace_expires_at"],
                "workspace_state": "expired" if self._workspace_expired(row) else "available",
                "artifacts": [dict(a) for a in db.execute("SELECT id,name,media_type,size FROM service_task_artifacts WHERE task_id=?", (row["id"],))]}

    def _owned(self, db, task_id, owner, agent_id=""):
        row = db.execute("SELECT * FROM service_tasks WHERE id=? AND user_id=? AND agent_id=? "
                         "AND (expires_at>? OR status NOT IN ('completed','failed','cancelled'))",
                         (task_id, owner, agent_id, now())).fetchone()
        if row is None:
            raise KeyError("任务不存在、已到期或无权访问")
        return row

    def get(self, principal, task_id) -> dict:
        owner = require_scope(principal, "tasks:read")
        with self.store.connect() as db:
            return self._visible(self._view(db, self._owned(db, task_id, owner, principal.get("agent_id", ""))), principal)

    def read_results(self, principal, task_id) -> dict:
        owner = require_scope(principal, "tasks:read")
        with self.store.connect() as db:
            row = self._owned(db, task_id, owner, principal.get("agent_id", ""))
            result = json.loads(row["result_json"]) if row["result_json"] else None
            return {"task_id": task_id, "status": row["status"], "ready": result is not None,
                    "text": result["text"] if result else None, "files": result["files"] if result else [],
                    "updated_at": result["updated_at"] if result else None,
                    "error": None if result else row["error"] or ("该历史任务没有结构化结果" if row["status"] == "completed" else None),
                    "workspace_state": "expired" if self._workspace_expired(row) else "available"}

    def list(self, principal, *, limit=50, offset=0, context_id=None, status=None, updated_after=None) -> dict:
        owner = require_scope(principal, "tasks:read")
        where, args = "user_id=? AND agent_id=? AND (expires_at>? OR status NOT IN ('completed','failed','cancelled'))", [owner, principal.get("agent_id", ""), now()]
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
            return {"tasks": [self._visible(self._view(db, r), principal) for r in rows], "total": total}

    def _workspace_expired(self, row):
        if row["workspace_evicted_at"] or row["status"] in TERMINAL and not row["session_id"]:
            return True
        state = self.service.sessions.get(row["session_id"])
        active = state.active_run_holder["run"] if state else None
        if row["status"] not in TERMINAL or active and not active.finished:
            return False
        return row["expires_at"] <= now() or bool(row["workspace_expires_at"] and row["workspace_expires_at"] <= now())

    def temporary_workspace(self, token: str) -> dict | None:
        """Resolve a capability for one task only; never revive expired/deleted sessions."""
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM service_tasks WHERE workspace_token=?", (token,)).fetchone()
            if row is None or self._workspace_expired(row):
                return None
            account = db.execute("SELECT enabled,expires_at,scopes FROM service_accounts WHERE user_id=?", (row["user_id"],)).fetchone()
            if account and (not account["enabled"] or account["expires_at"] <= now() or not SCOPES <= set(json.loads(account["scopes"]))):
                return None
            if row["session_id"] and self.store.session_by_id(row["session_id"]) is None:
                return None
            if row["session_id"] and not (self.service.data_root / "users" / row["user_id"] / "sessions" / row["session_id"]).is_dir():
                return None
            if not row["session_id"] and row["status"] in TERMINAL:
                return None
            return {**dict(row), "snapshot": json.loads(row["input_json"]).get("agent_snapshot") or {}}

    def workspace_expiry(self, opened: bool):
        seconds = self.settings.tmp_idle_seconds if opened else self.settings.machine_idle_seconds
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()

    def open_workspace(self, token, *, activity=False):
        with self._lock:
            task = self.temporary_workspace(token)
            if task is None:
                return None
            # Only the first browser bootstrap and actual interaction renew the idle lease.
            if activity or not task["workspace_opened_at"]:
                with self.store.connect() as db:
                    db.execute("UPDATE service_tasks SET workspace_opened_at=COALESCE(workspace_opened_at,?),"
                               "workspace_last_active_at=?,workspace_expires_at=? WHERE id=?",
                               (now(), now(), self.workspace_expiry(True), task["id"]))
                task = self.temporary_workspace(token)
            return task

    def create_workspace_run(self, token, user_input, attachments):
        with self._lock:
            task = self.temporary_workspace(token)
            if task is None or not task["session_id"]:
                raise KeyError("该节点已过期，请重新申请")
            if task["status"] not in TERMINAL:
                raise ValueError("请等待当前机器任务结束后继续对话")
            session = self.service.get_session(task["session_id"])
            if session.lock.locked():
                raise ValueError("当前 Session 已有任务正在运行")
            with self.store.connect() as db:
                db.execute("UPDATE service_tasks SET expires_at=?,workspace_expires_at=?,workspace_last_active_at=? WHERE id=?",
                           (expiry(self.settings), self.workspace_expiry(True), now(), task["id"]))
            # Release previous continuation event buffers; the persisted history remains.
            for run in list(self.service.runs.values()):
                if run.session_id == session.id and run.finished:
                    self.service.run_manager.forget(run.id)
            return self.service.create_run(session.id, user_input, attachments)

    def workspace_finished(self, session, run):
        with self._lock:
            with self.store.connect() as db:
                task = db.execute("SELECT id,run_id,status FROM service_tasks WHERE session_id=?", (session.id,)).fetchone()
                if task is None or task["status"] not in TERMINAL or task["run_id"] == run.id:
                    return
                db.execute("UPDATE service_tasks SET expires_at=?,workspace_expires_at=?,workspace_last_active_at=? WHERE id=?",
                           (expiry(self.settings), self.workspace_expiry(True), now(), task["id"]))
                self._event(db, task["id"], "workspace.run." + run.status, {"run_id": run.id, "reply": run.reply, "error": run.error})
                if run.status == "completed":
                    self._record_results(db, task["id"], session, run)
            self.capture_files(task["id"])
            self.service.evict_session(session.id)

    def cancel(self, principal, task_id) -> dict:
        owner = require_scope(principal, "tasks:cancel")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._owned(db, task_id, owner, principal.get("agent_id", ""))
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
            self._owned(db, task_id, owner, principal.get("agent_id", ""))
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
            row = self._owned(db, task_id, owner, principal.get("agent_id", ""))
            if self._workspace_expired(row):
                raise KeyError("临时节点已过期，产物文件已不可读取")
            item = db.execute("SELECT * FROM service_task_artifacts WHERE task_id=? AND id=?", (task_id, artifact_id)).fetchone()
        if item is None or not row["session_id"]:
            raise KeyError("产物不存在")
        root = (self.service.data_root / "users" / owner / "sessions" / row["session_id"]).resolve()
        candidate = (root / item["path"]).resolve()
        if (not root.is_relative_to(self.service.data_root) or not candidate.is_relative_to(root)
                or candidate == root or not candidate.is_file()):
            raise KeyError("产物不存在")
        return candidate, item["media_type"]

    def _file_context(self, db, principal, task_id):
        owner = require_scope(principal, "artifacts:read")
        row = self._owned(db, task_id, owner, principal.get("agent_id", ""))
        if self._workspace_expired(row):
            raise KeyError("临时节点已过期，文件已不可读取")
        root = session_root(self.service.data_root, owner, row["session_id"]) if row["session_id"] else None
        if row["session_id"] and root is None:
            raise KeyError("任务文件已不可读取")
        return row, root

    @staticmethod
    def _safe_file_path(root, relative, expected_type=None):
        parts = PurePosixPath(relative).parts
        if (not parts or parts[0] not in ROOTS or PurePosixPath(relative).is_absolute()
                or any(part in {".", ".."} for part in parts) or "\\" in relative):
            raise KeyError("文件不存在或不可读取")
        current = root
        try:
            for part in parts:
                current = current / part
                if _linked(current.lstat()) or not current.resolve().is_relative_to(root):
                    raise KeyError("文件不存在或不可读取")
            info = current.lstat()
            kind = "directory" if stat.S_ISDIR(info.st_mode) else "file" if stat.S_ISREG(info.st_mode) else None
            if kind is None or (expected_type is not None and kind != expected_type):
                raise KeyError("文件不存在或类型已变化，请重新列出目录")
            return current, kind, info
        except OSError as exc:
            raise KeyError("文件不存在或不可读取") from exc

    def _file_ref(self, db, root, task_id, file_id):
        if type(file_id) is not int or not 1 <= file_id <= 2**63 - 1:
            raise ValueError("文件序号须为正整数")
        item = db.execute("SELECT path,type FROM service_task_file_refs WHERE task_id=? AND file_id=?",
                          (task_id, file_id)).fetchone()
        if item is None or root is None:
            raise KeyError("文件序号不存在，请先调用 list_file")
        path, kind, info = self._safe_file_path(root, item["path"], item["type"])
        return path, kind, info

    def list_file(self, principal, task_id, directory_id=None):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row, root = self._file_context(db, principal, task_id)
            result = {"task_id": task_id, "agent_id": row["agent_id"], "directory_id": directory_id,
                      "ready": root is not None, "files": []}
            if root is None:
                if directory_id is not None:
                    raise KeyError("任务文件尚未就绪")
                return result
            if directory_id is None:
                children = [root / name for name in ROOTS]
            else:
                directory, kind, _ = self._file_ref(db, root, task_id, directory_id)
                if kind != "directory":
                    raise ValueError("directory_id 必须指向文件夹")
                try:
                    children = list(directory.iterdir())
                except OSError as exc:
                    raise KeyError("文件夹已不可读取") from exc
            entries = []
            for child in children:
                relative = child.relative_to(root).as_posix()
                try:
                    path, kind, info = self._safe_file_path(root, relative)
                except KeyError:
                    continue
                entries.append((path, kind, info, relative))
            next_id = db.execute("SELECT COALESCE(MAX(file_id),0)+1 FROM service_task_file_refs WHERE task_id=?",
                                 (task_id,)).fetchone()[0]
            for path, kind, info, relative in sorted(entries, key=lambda entry: (entry[1] != "directory", entry[0].name.casefold(), entry[0].name)):
                existing = db.execute("SELECT file_id FROM service_task_file_refs WHERE task_id=? AND path=? AND type=?",
                                      (task_id, relative, kind)).fetchone()
                file_id = existing[0] if existing else next_id
                if existing is None:
                    db.execute("INSERT INTO service_task_file_refs VALUES(?,?,?,?)", (task_id, file_id, relative, kind))
                    next_id += 1
                result["files"].append({"file_id": file_id, "name": path.name, "type": kind,
                                        "size": info.st_size if kind == "file" else None})
            return result

    def file_info(self, principal, task_id, file_id):
        with self.store.connect() as db:
            _, root = self._file_context(db, principal, task_id)
            path, kind, info = self._file_ref(db, root, task_id, file_id)
        return {"task_id": task_id, "file_id": file_id, "name": path.name + ".zip" if kind == "directory" else path.name,
                "type": kind, "size": info.st_size if kind == "file" else None,
                "media_type": "application/zip" if kind == "directory" else mimetypes.guess_type(path.name)[0] or "application/octet-stream"}

    def _record_results(self, db, task_id, session, run):
        if run.structured_result is None:
            raise ValueError("Agent 未通过 submit_results 成功提交本轮答案，请重试任务")
        result = validate_result(run.structured_result)
        root = session_root(self.service.data_root, session.user_id, session.id)
        if root is None:
            raise ValueError("任务目录已不可读取，未登记最终产物")
        verified = [(dict(item, description=self.service.web_text(session.id, item["description"])), path, kind, info)
                    for item, path, kind, info in verify_result_files(result, root)]
        public_text = self.service.web_text(session.id, result["text"])
        # Acquire the writer lock before allocating IDs, shared with concurrent list_file.
        db.execute("DELETE FROM service_task_artifacts WHERE task_id=?", (task_id,))
        next_id = db.execute("SELECT COALESCE(MAX(file_id),0)+1 FROM service_task_file_refs WHERE task_id=?", (task_id,)).fetchone()[0]
        files = []
        for item, path, kind, info in verified:
            relative = path.relative_to(root).as_posix()
            existing = db.execute("SELECT file_id FROM service_task_file_refs WHERE task_id=? AND path=? AND type=?", (task_id, relative, kind)).fetchone()
            file_id = existing[0] if existing else next_id
            if existing is None:
                db.execute("INSERT INTO service_task_file_refs VALUES(?,?,?,?)", (task_id, file_id, relative, kind))
                next_id += 1
            files.append({"file_id": file_id, "name": path.name, "path": relative, "type": kind,
                          "size": info.st_size if kind == "file" else None,
                          "description": item["description"]})
            # Keep existing REST/A2A file links compatible, but only for declared final files.
            if kind == "file":
                artifact_id = hashlib.sha256(relative.encode()).hexdigest()[:20]
                db.execute("INSERT INTO service_task_artifacts VALUES(?,?,?,?,?,?)", (
                    artifact_id, task_id, relative, relative, mimetypes.guess_type(path.name)[0] or "application/octet-stream", info.st_size))
        public = {"text": public_text, "files": files, "updated_at": now()}
        db.execute("UPDATE service_tasks SET result_json=? WHERE id=?", (json.dumps(public, ensure_ascii=False), task_id))
        return public

    def download_file(self, principal, task_id, file_id):
        with self.store.connect() as db:
            _, root = self._file_context(db, principal, task_id)
            path, kind, _ = self._file_ref(db, root, task_id, file_id)
        if kind == "file":
            return path, mimetypes.guess_type(path.name)[0] or "application/octet-stream", path.name, False
        with tempfile.NamedTemporaryFile(prefix="umeko-task-download-", suffix=".zip", delete=False) as output:
            archive_path = Path(output.name)
        try:
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                pending = [path]
                while pending:
                    current = pending.pop()
                    self._safe_file_path(root, current.relative_to(root).as_posix(), "directory")
                    archive.writestr(current.relative_to(path.parent).as_posix() + "/", b"")
                    with os.scandir(current) as iterator:
                        for entry in iterator:
                            child, child_kind, _ = self._safe_file_path(root, Path(entry.path).relative_to(root).as_posix())
                            if child_kind == "directory":
                                pending.append(child)
                            else:
                                archive.write(child, child.relative_to(path.parent).as_posix())
            return archive_path, "application/zip", path.name + ".zip", True
        except OSError as exc:
            archive_path.unlink(missing_ok=True)
            raise KeyError("文件夹内容已变化或不可读取，请重新列出目录") from exc
        except BaseException:
            archive_path.unlink(missing_ok=True)
            raise

    def _schedule(self):
        last_gc = 0.0
        while not self._stop.is_set():
            try:
                if time.monotonic() - last_gc > 60:
                    last_gc = time.monotonic()
                    self.cleanup()
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

    def capture_files(self, task_id):
        from .file_manifest import capture, session_root
        with self.store.connect() as db:
            row = db.execute("SELECT user_id,session_id FROM service_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None or not row["session_id"]:
            return
        root = session_root(self.service.data_root, row["user_id"], row["session_id"])
        snapshot = capture(root) if root is not None else None
        if snapshot is not None:
            with self.store.connect() as db:
                db.execute("UPDATE service_tasks SET file_manifest_json=? WHERE id=?",
                           (json.dumps(snapshot, ensure_ascii=False), task_id))

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
            session = self.service.create_session(user_id=row["user_id"], title="服务任务 " + task_id[-8:],
                                                  agent_snapshot=payload.get("agent_snapshot"), machine_results=True)
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
                if status == "completed":
                    reply = self._record_results(db, task_id, session, run)["text"]
                expires = (datetime.now(timezone.utc) + timedelta(seconds=self.settings.task_retention_seconds)).isoformat()
                db.execute("UPDATE service_tasks SET status=?,reply=?,error=?,updated_at=?,completed_at=?,expires_at=? WHERE id=?",
                           (status, reply, error, stamp, stamp, expires, task_id))
                self._event(db, task_id, "task." + status, {"reply": reply, "error": error})
        except Exception as exc:
            error = self.service.web_text(session.id, str(exc)) if session else "任务初始化失败，请管理员检查配置"
            with self.store.connect() as db:
                db.execute("UPDATE service_tasks SET status='failed',error=?,completed_at=?,updated_at=?,expires_at=? WHERE id=?",
                           (error, now(), now(), expiry(self.settings), task_id))
                self._event(db, task_id, "task.failed", {"error": error})
            logger.exception("Machine task failed: %s", task_id)
        finally:
            with self.store.connect() as db:
                row = db.execute("SELECT workspace_opened_at FROM service_tasks WHERE id=?", (task_id,)).fetchone()
                if row:
                    db.execute("UPDATE service_tasks SET workspace_expires_at=? WHERE id=?", (self.workspace_expiry(bool(row["workspace_opened_at"])), task_id))
            if session:
                try:
                    self.capture_files(task_id)
                except Exception:
                    logger.exception("Failed to capture task file metadata: %s", task_id)
            if session and (run is None or run.finished) and not self.service.active_run(session.id):
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
        self.cleanup_workspaces()
        with self.store.connect() as db:
            rows = db.execute("SELECT id,session_id FROM service_tasks WHERE expires_at<=? "
                              "AND status IN ('completed','failed','cancelled')", (now(),)).fetchall()
        count = 0
        for row in rows:
            with self._lock:
                if row["id"] in self._active:
                    continue
                # Recheck the lease under the same lock used by browser continuation.
                with self.store.connect() as db:
                    current = db.execute("SELECT expires_at FROM service_tasks WHERE id=?", (row["id"],)).fetchone()
                if current is None or current["expires_at"] > now():
                    continue
                state = self.service.sessions.get(row["session_id"])
                if state and (state.lock.locked() or self.service.active_run(state.id)):
                    continue
                if row["session_id"] and self.store.session_by_id(row["session_id"]):
                    self.service.delete_session_admin(row["session_id"])
                for run in list(self.service.runs.values()):
                    if run.session_id == row["session_id"] and run.finished:
                        self.service.run_manager.forget(run.id)
                self._remove_staging(row["id"])
                with self.store.connect() as db:
                    db.execute("DELETE FROM service_tasks WHERE id=?", (row["id"],))
                count += 1
        return count

    def cleanup_workspaces(self) -> int:
        """Reclaim temporary files and agents; keep database inspection records until task retention."""
        from .file_manifest import session_root
        with self.store.connect() as db:
            rows = db.execute("SELECT id FROM service_tasks WHERE workspace_evicted_at IS NULL AND workspace_expires_at<=? "
                              "AND status IN ('completed','failed','cancelled')", (now(),)).fetchall()
        count = 0
        for candidate in rows:
            with self._lock:
                with self.store.connect() as db:
                    row = db.execute("SELECT * FROM service_tasks WHERE id=?", (candidate["id"],)).fetchone()
                if row is None or row["id"] in self._active or row["workspace_evicted_at"] or row["workspace_expires_at"] > now():
                    continue
                state = self.service.sessions.get(row["session_id"])
                if state and (state.lock.locked() or self.service.active_run(state.id)):
                    continue
                if row["session_id"]:
                    self.capture_files(row["id"])
                    self.service.evict_session(row["session_id"])
                    root = session_root(self.service.data_root, row["user_id"], row["session_id"])
                    if root is not None:
                        shutil.rmtree(root)
                    self.service.remove_script_trust(row["session_id"])
                    for run in list(self.service.runs.values()):
                        if run.session_id == row["session_id"] and run.finished:
                            self.service.run_manager.forget(run.id)
                with self.store.connect() as db:
                    db.execute("UPDATE service_tasks SET workspace_evicted_at=? WHERE id=?", (now(), row["id"]))
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
