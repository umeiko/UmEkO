"""Administrator approval of exact file versions in the shared skill library."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import threading

from ..skill_layout import member_path, slug
from ..skill_security import _digests, _regular


def skill_maintenance(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self.skill_approvals.lock:
            return method(self, *args, **kwargs)
    return guarded


class SkillApprovals:
    def __init__(self, service):
        self.service = service
        self.lock = threading.RLock()
        with service.store.connect() as db:
            # Earlier per-session maintenance events did not approve a library
            # version for future dispatch and are not used as authorizations.
            db.execute("""CREATE TABLE IF NOT EXISTS skill_file_approvals (
                pack TEXT NOT NULL, member TEXT NOT NULL, md5 TEXT NOT NULL, sha256 TEXT NOT NULL,
                actor TEXT NOT NULL, actor_id TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(pack, member))""")
            db.execute("""CREATE TABLE IF NOT EXISTS skill_file_approval_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, pack TEXT NOT NULL, member TEXT NOT NULL,
                md5 TEXT NOT NULL, sha256 TEXT NOT NULL, actor TEXT NOT NULL,
                actor_id TEXT NOT NULL, created_at TEXT NOT NULL)""")

    def source(self, pack, member):
        pack = slug(pack)
        base = self.service._skills_library_dir().resolve()
        path = member_path(base, pack, member)
        relative = path.relative_to(base / pack).as_posix()
        if not ((path.suffix.casefold() == ".py" and relative.startswith("scripts/"))
                or path.name.casefold() == "config.json"):
            raise ValueError("仅支持技能 scripts/ 下的 Python 文件与 config.json")
        return pack, relative, _regular(path)

    def approved_files(self, pack):
        """Host-only digests, never derived from user/session bytes."""
        with self.lock, self.service.store.connect() as db:
            return {row["member"]: {"md5": row["md5"], "sha256": row["sha256"]}
                    for row in db.execute("SELECT member,md5,sha256 FROM skill_file_approvals WHERE pack=?", (slug(pack),))}

    def status(self, pack, member):
        with self.lock:
            pack, member, data = self.source(pack, member)
            current = _digests(data)
            with self.service.store.connect() as db:
                row = db.execute("SELECT * FROM skill_file_approvals WHERE pack=? AND member=?", (pack, member)).fetchone()
            approved = dict(row) if row else None
            trusted = bool(approved and all(approved[key] == current[key] for key in current))
            return {"pack": pack, "member": member, "current": {**current, "size": len(data)},
                    "readonly": True, "trusted": trusted,
                    "status": "trusted" if trusted else "changed" if approved else "unlisted",
                    "approved": approved}

    def approve(self, pack, member, expected_sha256, *, actor, actor_id=""):
        with self.lock:
            pack, member, data = self.source(pack, member)
            current = _digests(data)
            if current["sha256"] != expected_sha256:
                raise RuntimeError("技能库文件已变化，请刷新安全状态后重试")
            created_at = datetime.now(timezone.utc).isoformat()
            values = (pack, member, current["md5"], current["sha256"], actor, actor_id, created_at)
            # Approval and audit commit together. No session files or records
            # are inspected, rewritten or reissued by this operation.
            with self.service.store.connect() as db:
                db.execute("INSERT INTO skill_file_approvals VALUES(?,?,?,?,?,?,?) "
                           "ON CONFLICT(pack,member) DO UPDATE SET md5=excluded.md5,sha256=excluded.sha256,"
                           "actor=excluded.actor,actor_id=excluded.actor_id,created_at=excluded.created_at", values)
                event_id = db.execute("INSERT INTO skill_file_approval_events "
                                      "(pack,member,md5,sha256,actor,actor_id,created_at) VALUES(?,?,?,?,?,?,?)", values).lastrowid
            # Re-read so an out-of-process disk change is reported as changed.
            return {**self.status(pack, member), "event_id": event_id}
