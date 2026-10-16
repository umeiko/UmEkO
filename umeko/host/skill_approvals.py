"""Administrator-only inspection and reissue from the trusted skill library."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import json
import os
from pathlib import Path
import tempfile
import threading

from ..file_operations import bounded_path
from ..skill_layout import checked, member_path, slug
from ..skill_security import _digests, _regular


def skill_maintenance(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self.skill_approvals.lock:
            return method(self, *args, **kwargs)
    return guarded


def atomic_write(path: Path, data: bytes):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".skill-approval-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class SkillApprovals:
    def __init__(self, service):
        self.service = service
        self.lock = threading.RLock()
        with service.store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS skill_approval_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, pack TEXT NOT NULL, member TEXT NOT NULL,
                actor TEXT NOT NULL, actor_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, md5 TEXT NOT NULL, sha256 TEXT NOT NULL,
                redispatch INTEGER NOT NULL, result_json TEXT NOT NULL)""")
            if "actor_id" not in {r["name"] for r in db.execute("PRAGMA table_info(skill_approval_events)")}:
                db.execute("ALTER TABLE skill_approval_events ADD COLUMN actor_id TEXT NOT NULL DEFAULT ''")

    def source(self, pack, member):
        pack = slug(pack)
        base = self.service._skills_library_dir().resolve()
        path = member_path(base, pack, member)
        relative = path.relative_to(base / pack).as_posix()
        if not ((path.suffix.casefold() == ".py" and relative.startswith("scripts/"))
                or path.name.casefold() == "config.json"):
            raise ValueError("仅支持技能 scripts/ 下的 Python 文件与 config.json")
        return pack, relative, _regular(path)

    def _candidates(self, pack):
        with self.service.store.connect() as db:
            rows = db.execute("SELECT s.id,s.user_id,s.title,u.username FROM agent_sessions s "
                              "JOIN users u ON u.id=s.user_id ORDER BY s.created_at DESC").fetchall()
        for row in rows:
            record = checked(self.service.data_root / "skill_trust", row["id"] + "/" + pack + ".json")
            if record.is_file():
                yield dict(row), record

    def _inspect(self, row, record, pack, member, current):
        result = {"session_id": row["id"], "username": row["username"], "title": row["title"],
                  "status": "invalid", "approved": None, "actual": None, "matches_library": False}
        try:
            manifest = json.loads(_regular(record))
            if (not isinstance(manifest, dict) or manifest.get("version") != 1 or manifest.get("pack") != pack
                    or not isinstance(manifest.get("files"), dict) or not isinstance(manifest.get("scripts"), list)):
                raise ValueError("批准记录格式不正确")
            root = self.service.data_root / "users" / row["user_id"] / "sessions" / row["id"]
            target = bounded_path(self.service.data_root, root / "client/skills" / pack / member)
            expected = manifest["files"].get(member)
            result["approved"] = expected
            if not target.is_file():
                result["status"] = "missing"
                return result, manifest, target
            actual = _digests(_regular(target))
            result["actual"] = actual
            result["matches_library"] = actual == current
            if expected is None or (target.suffix.casefold() == ".py" and member not in manifest["scripts"]):
                result["status"] = "unlisted"
            elif expected != actual:
                result["status"] = "mismatch"
            else:
                result["status"] = "approved" if actual == current else "old_version"
            return result, manifest, target
        except (OSError, ValueError, TypeError, KeyError) as exc:
            result["error"] = type(exc).__name__
            return result, None, None

    def status(self, pack, member, *, offset=0, limit=30):
        with self.lock:
            pack, member, data = self.source(pack, member)
            current = _digests(data)
            rows = [self._inspect(row, record, pack, member, current)[0]
                    for row, record in self._candidates(pack)]
            with self.service.store.connect() as db:
                events = [dict(row) for row in db.execute("SELECT * FROM skill_approval_events "
                          "WHERE pack=? AND member=? ORDER BY id DESC LIMIT 5", (pack, member))]
            for event in events:
                event["result"] = json.loads(event.pop("result_json"))
                event["matches_current"] = event["sha256"] == current["sha256"] and event["md5"] == current["md5"]
            counts = {key: sum(r["status"] == key for r in rows)
                      for key in ("approved", "old_version", "mismatch", "unlisted", "missing", "invalid")}
            return {"pack": pack, "member": member, "current": {**current, "size": len(data)},
                    "readonly": True, "counts": counts, "total": len(rows), "offset": offset,
                    "limit": limit, "sessions": rows[offset:offset + limit], "events": events}

    def approve(self, pack, member, expected_sha256, *, actor, actor_id="", redispatch=False):
        with self.lock:
            pack, member, data = self.source(pack, member)
            current = _digests(data)
            if current["sha256"] != expected_sha256:
                raise RuntimeError("技能库文件已变化，请刷新安全状态后重试")
            created_at = datetime.now(timezone.utc).isoformat()
            outcome = {"updated": 0, "unchanged": 0, "skipped_mismatch": 0, "skipped_busy": 0,
                       "skipped_invalid": 0, "failed": 0, "status": "started"}
            with self.service.store.connect() as db:
                event_id = db.execute("INSERT INTO skill_approval_events(pack,member,actor,actor_id,created_at,md5,sha256,redispatch,result_json) "
                           "VALUES(?,?,?,?,?,?,?,?,?)", (pack, member, actor, actor_id, created_at, current["md5"],
                           current["sha256"], int(redispatch), json.dumps(outcome))).lastrowid
            busy_sessions = {run.session_id for run in self.service.runs.values()
                             if run.status not in {"completed", "failed", "cancelled"}}
            for row, record in self._candidates(pack):
                state = self.service.sessions.get(row["id"])
                active = state.active_run_holder["run"] if state else None
                if row["id"] in busy_sessions or active is not None and active.status not in {"completed", "failed", "cancelled"}:
                    outcome["skipped_busy"] += 1
                    continue
                acquired = state.lock.acquire(blocking=False) if state else True
                if not acquired:
                    outcome["skipped_busy"] += 1
                    continue
                try:
                    info, manifest, target = self._inspect(row, record, pack, member, current)
                    if manifest is None or info["status"] == "invalid":
                        outcome["skipped_invalid"] += 1
                        continue
                    if not info["matches_library"] and not redispatch:
                        outcome["skipped_mismatch"] += 1
                        continue
                    if info["status"] == "approved":
                        outcome["unchanged"] += 1
                        continue
                    if not target.parent.is_dir():
                        outcome["skipped_invalid"] += 1
                        continue
                    old = _regular(target) if target.exists() else None
                    manifest["files"][member] = current
                    if member.endswith(".py") and member not in manifest["scripts"]:
                        manifest["scripts"].append(member)
                    if redispatch:
                        atomic_write(target, data)
                    try:
                        atomic_write(record, json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8"))
                    except OSError:
                        if redispatch:
                            atomic_write(target, old) if old is not None else target.unlink(missing_ok=True)
                        raise
                    outcome["updated"] += 1
                except (OSError, ValueError, TypeError, KeyError):
                    outcome["failed"] += 1
                finally:
                    if state:
                        state.lock.release()
            outcome["status"] = "completed"
            with self.service.store.connect() as db:
                db.execute("UPDATE skill_approval_events SET result_json=? WHERE id=?", (json.dumps(outcome), event_id))
            return {"event_id": event_id, "pack": pack, "member": member, **outcome}
