"""Administrator approval of exact file versions in the shared skill library."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import os
from pathlib import Path
import threading

from ..skill_layout import member_path, slug
from ..skill_security import SkillSecurityError, _digests, _regular


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
            if "approval_id" not in {r["name"] for r in db.execute("PRAGMA table_info(skill_file_approvals)")}:
                db.execute("ALTER TABLE skill_file_approvals ADD COLUMN approval_id INTEGER NOT NULL DEFAULT 0")
            if "action" not in {r["name"] for r in db.execute("PRAGMA table_info(skill_file_approval_events)")}:
                db.execute("ALTER TABLE skill_file_approval_events ADD COLUMN action TEXT NOT NULL DEFAULT 'approve'")
            db.execute("""CREATE TABLE IF NOT EXISTS skill_file_revocations (
                pack TEXT NOT NULL, member TEXT NOT NULL, event_id INTEGER NOT NULL,
                md5 TEXT NOT NULL, sha256 TEXT NOT NULL, actor TEXT NOT NULL,
                actor_id TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(pack,member))""")

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
            return {row["member"]: {key: row[key] for key in ("md5", "sha256", "approval_id")}
                    for row in db.execute("SELECT member,md5,sha256,approval_id FROM skill_file_approvals WHERE pack=?", (slug(pack),))}

    def check_revocations(self, pack, expected):
        """Apply revocations to issued snapshots without rewriting old records."""
        with self.lock, self.service.store.connect() as db:
            for row in db.execute("SELECT member,event_id FROM skill_file_revocations WHERE pack=?", (slug(pack),)):
                if row["member"] in expected and expected[row["member"]].get("approval_id", 0) <= row["event_id"]:
                    raise SkillSecurityError("技能文件已被管理员移出可信区，拒绝执行：" + row["member"])

    @staticmethod
    def _describe(pack, member, data, approved, revoked, *, error=None):
        current = {**_digests(data), "size": len(data)} if data is not None else None
        trusted = bool(current and approved and all(approved[key] == current[key] for key in ("md5", "sha256")))
        state = ("invalid" if error else "missing" if current is None else "trusted" if trusted else
                 "changed" if approved else "revoked" if revoked else "unlisted")
        return {"pack": pack, "member": member, "current": current, "readonly": True,
                "trusted": trusted, "status": state, "approved": approved, "revoked": revoked,
                "kind": "python" if member.casefold().endswith(".py") else "config",
                "approvable": data is not None and not error, "error": error}

    def status(self, pack, member):
        with self.lock:
            pack, member, data = self.source(pack, member)
            with self.service.store.connect() as db:
                row = db.execute("SELECT * FROM skill_file_approvals WHERE pack=? AND member=?", (pack, member)).fetchone()
                revoked = db.execute("SELECT * FROM skill_file_revocations WHERE pack=? AND member=?", (pack, member)).fetchone()
            approved = dict(row) if row else None
            return self._describe(pack, member, data, approved, dict(revoked) if revoked else None)

    def catalog(self, *, q="", pack="", status="", kind="", offset=0, limit=50, selection=False):
        from ..file_operations import is_link
        if pack:
            pack = slug(pack)
        with self.lock:
            with self.service.store.connect() as db:
                approvals = {(r["pack"], r["member"]): dict(r) for r in db.execute("SELECT * FROM skill_file_approvals")}
                revocations = {(r["pack"], r["member"]): dict(r) for r in db.execute("SELECT * FROM skill_file_revocations")}
            candidates = set(approvals) | set(revocations)
            library = self.service._skills_library_dir().resolve()
            # Never traverse symlink/junction directories, including packages.
            for package in sorted(library.iterdir()) if library.is_dir() else ():
                if not package.is_dir() or is_link(package):
                    continue
                try:
                    slug(package.name)
                except ValueError:
                    continue
                for parent, directories, names in os.walk(package, followlinks=False):
                    directories[:] = [name for name in directories if name != "__pycache__" and not is_link(Path(parent) / name)]
                    for name in names:
                        if name.casefold().endswith(".py") or name.casefold() == "config.json":
                            candidates.add((package.name, (Path(parent) / name).relative_to(package).as_posix()))
            packs = sorted({p for p, _ in candidates})
            rows = []
            needle = q.strip().casefold()
            for name, member in sorted(candidates):
                file_kind = "python" if member.casefold().endswith(".py") else "config"
                if pack and name != pack or kind and kind != file_kind or needle and needle not in (name + "/" + member).casefold():
                    continue
                data, error = None, None
                try:
                    _, _, data = self.source(name, member)
                except FileNotFoundError:
                    pass
                except (ValueError, OSError):
                    # _regular also reports missing files as a security error.
                    path = library / name / member
                    try:
                        unsafe = path.exists() or is_link(path)
                    except FileNotFoundError:
                        unsafe = False
                    except OSError:
                        unsafe = True
                    if unsafe:
                        error = "文件不可读或路径不安全"
                row = self._describe(name, member, data, approvals.get((name, member)), revocations.get((name, member)), error=error)
                rows.append(row)
            counts = {state: sum(r["status"] == state for r in rows)
                      for state in ("trusted", "unlisted", "changed", "revoked", "missing", "invalid")}
            filtered = [row for row in rows if not status or row["status"] == status]
            if selection:
                return {"items": [{"pack": r["pack"], "member": r["member"], "status": r["status"],
                                   "sha256": r["current"]["sha256"] if r["current"] else None,
                                   "approved_sha256": r["approved"]["sha256"] if r["approved"] else None,
                                   "approvable": r["approvable"]} for r in filtered], "total": len(filtered)}
            return {"items": filtered[offset:offset + limit], "total": len(filtered), "offset": offset,
                    "limit": limit, "counts": counts, "packs": packs}

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
                event_id = db.execute("INSERT INTO skill_file_approval_events "
                                      "(pack,member,md5,sha256,actor,actor_id,created_at,action) VALUES(?,?,?,?,?,?,?,'approve')", values).lastrowid
                db.execute("INSERT INTO skill_file_approvals(pack,member,md5,sha256,actor,actor_id,created_at,approval_id) VALUES(?,?,?,?,?,?,?,?) "
                           "ON CONFLICT(pack,member) DO UPDATE SET md5=excluded.md5,sha256=excluded.sha256,"
                           "actor=excluded.actor,actor_id=excluded.actor_id,created_at=excluded.created_at,approval_id=excluded.approval_id", (*values, event_id))
            # Re-read so an out-of-process disk change is reported as changed.
            return {**self.status(pack, member), "event_id": event_id}

    def revoke(self, pack, member, expected_sha256, *, actor, actor_id=""):
        # Validate names without following a potentially replaced/missing file:
        # removing approval must remain possible after deletion or tampering.
        pack = slug(pack)
        parts = member.split("/")
        if (len(parts) < 2 or parts[0] not in {"scripts", "references", "assets"}
                or any(not part or part in {".", ".."} or ":" in part or "\\" in part or part.rstrip(" .") != part for part in parts)
                or not (member.casefold().endswith(".py") and parts[0] == "scripts" or parts[-1].casefold() == "config.json")):
            raise ValueError("非法技能文件路径")
        with self.lock, self.service.store.connect() as db:
            row = db.execute("SELECT * FROM skill_file_approvals WHERE pack=? AND member=?", (pack, member)).fetchone()
            if row is None or row["sha256"] != expected_sha256:
                raise RuntimeError("可信记录已变化，请刷新安全状态后重试")
            created_at = datetime.now(timezone.utc).isoformat()
            values = (pack, member, row["md5"], row["sha256"], actor, actor_id, created_at)
            event_id = db.execute("INSERT INTO skill_file_approval_events "
                                  "(pack,member,md5,sha256,actor,actor_id,created_at,action) VALUES(?,?,?,?,?,?,?,'revoke')", values).lastrowid
            db.execute("INSERT INTO skill_file_revocations(pack,member,md5,sha256,actor,actor_id,created_at,event_id) VALUES(?,?,?,?,?,?,?,?) "
                       "ON CONFLICT(pack,member) DO UPDATE SET md5=excluded.md5,sha256=excluded.sha256,actor=excluded.actor,"
                       "actor_id=excluded.actor_id,created_at=excluded.created_at,event_id=excluded.event_id", (*values, event_id))
            db.execute("DELETE FROM skill_file_approvals WHERE pack=? AND member=?", (pack, member))
        return {"pack": pack, "member": member, "trusted": False, "status": "revoked", "event_id": event_id}

    def batch(self, action, items, *, actor, actor_id=""):
        if action not in {"approve", "revoke"}:
            raise ValueError("未知的可信区操作")
        identities = [(item["pack"], item["member"]) for item in items]
        if len(set(identities)) != len(identities):
            raise ValueError("批次包含重复文件")
        method = self.approve if action == "approve" else self.revoke
        results = []
        for item in items:
            try:
                result = method(item["pack"], item["member"], item["sha256"], actor=actor, actor_id=actor_id)
                if action == "approve" and not result["trusted"]:
                    raise RuntimeError("技能库文件已变化，请刷新安全状态后重试")
                results.append({**item, "ok": True, "status": result["status"]})
            except (ValueError, OSError, RuntimeError) as exc:
                message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "文件读写失败"
                results.append({**item, "ok": False, "error": message})
        return {"action": action, "results": results, "succeeded": sum(r["ok"] for r in results),
                "failed": sum(not r["ok"] for r in results)}
