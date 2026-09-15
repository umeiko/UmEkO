from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """用户、Session、消息、上下文摘要与 Skill 挂载的 SQLite 持久化。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _init(self):
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
              password_hash TEXT NOT NULL, created_at TEXT NOT NULL,
              avatar BLOB, avatar_mime TEXT
            );
            CREATE TABLE IF NOT EXISTS auth_tokens (
              token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_sessions (
              id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              context_summary TEXT, context_cutoff_id INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_agent_sessions_user_updated
              ON agent_sessions(user_id, updated_at DESC);
            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
              role TEXT NOT NULL, content TEXT NOT NULL, attachments TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id, id);
            CREATE TABLE IF NOT EXISTS resource_mounts (
              session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
              kind TEXT NOT NULL CHECK(kind IN ('skills')),
              name TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY(session_id, kind, name)
            );
            CREATE TABLE IF NOT EXISTS app_config (
              key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS providers (
              id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
              base_url TEXT NOT NULL, api_key TEXT NOT NULL, proxy TEXT,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS provider_models (
              id TEXT PRIMARY KEY,
              provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
              name TEXT NOT NULL, vision INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              UNIQUE(provider_id, name)
            );
            CREATE TABLE IF NOT EXISTS user_model_prefs (
              user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
              main_model_id TEXT, sub_model_id TEXT, vision_model_id TEXT,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tool_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
              run_id TEXT,
              agent TEXT NOT NULL DEFAULT 'main',
              name TEXT NOT NULL,
              arguments TEXT,
              result TEXT,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tool_events_session
              ON tool_events(session_id, id);
            CREATE TABLE IF NOT EXISTS session_files (
              file_id TEXT PRIMARY KEY,
              session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
              path TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """)
            # 旧库迁移：users 补 role 列（管理员入口，role='admin'）
            cols = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
            if "role" not in cols:
                db.execute(
                    "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
                )
            # 旧库迁移：agent_sessions 补 model_override_id 列（用户会话级模型覆盖）
            session_cols = {
                row["name"] for row in db.execute("PRAGMA table_info(agent_sessions)")
            }
            if "model_override_id" not in session_cols:
                db.execute(
                    "ALTER TABLE agent_sessions ADD COLUMN model_override_id TEXT"
                )
            db.execute("PRAGMA optimize")

    @staticmethod
    def hash_password(password: str, salt: bytes | None = None) -> str:
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        return f"scrypt${salt.hex()}${digest.hex()}"

    @classmethod
    def verify_password(cls, password: str, encoded: str) -> bool:
        try:
            _, salt_hex, expected = encoded.split("$", 2)
            actual = cls.hash_password(password, bytes.fromhex(salt_hex)).split("$", 2)[2]
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    def create_user(self, username: str, password: str, role: str = "user") -> dict:
        username = username.strip()
        if len(username) < 3 or len(password) < 8:
            raise ValueError("用户名至少 3 个字符，密码至少 8 个字符")
        if role not in {"user", "admin"}:
            raise ValueError("role 只能是 user 或 admin")
        user = {
            "id": f"usr_{uuid.uuid4().hex}", "username": username,
            "created_at": _now(), "avatar_url": None, "role": role,
        }
        try:
            with self.connect() as db:
                db.execute(
                    "INSERT INTO users(id,username,password_hash,created_at,role) VALUES (?,?,?,?,?)", (
                        user["id"], username, self.hash_password(password),
                        user["created_at"], role,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在") from exc
        return user

    LOCAL_USERNAME = "local"

    def ensure_local_user(self) -> dict:
        """本地 IDE 场景的隐式单用户：不存在则以不可用口令创建。"""
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM users WHERE username=?", (self.LOCAL_USERNAME,)
            ).fetchone()
        if row:
            return {
                "id": row["id"], "username": row["username"],
                "avatar_url": "/v1/auth/avatar" if row["avatar"] is not None else None,
            }
        return self.create_user(self.LOCAL_USERNAME, secrets.token_urlsafe(24))

    @staticmethod
    def _user_view(row) -> dict:
        return {
            "id": row["id"], "username": row["username"],
            "role": row["role"] if "role" in row.keys() else "user",
            "avatar_url": "/v1/auth/avatar" if row["avatar"] is not None else None,
        }

    def authenticate(self, username: str, password: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (username.strip(),)).fetchone()
        if row and self.verify_password(password, row["password_hash"]):
            return self._user_view(row)
        return None

    def list_users(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("""
              SELECT users.*, COUNT(agent_sessions.id) AS session_count
              FROM users LEFT JOIN agent_sessions ON agent_sessions.user_id=users.id
              GROUP BY users.id ORDER BY users.created_at
            """).fetchall()
        return [
            {**self._user_view(row), "created_at": row["created_at"],
             "session_count": row["session_count"]}
            for row in rows
        ]

    def set_role(self, user_id: str, role: str) -> None:
        if role not in {"user", "admin"}:
            raise ValueError("role 只能是 user 或 admin")
        with self.connect() as db:
            if role == "user":
                admin_count = db.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE role='admin' AND id!=?",
                    (user_id,),
                ).fetchone()["c"]
                if admin_count == 0:
                    raise ValueError("至少需要保留一个管理员")
            result = db.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        if not result.rowcount:
            raise KeyError(user_id)

    def set_password(self, user_id: str, password: str) -> None:
        if len(password) < 8:
            raise ValueError("密码至少 8 个字符")
        with self.connect() as db:
            result = db.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (self.hash_password(password), user_id),
            )
        if not result.rowcount:
            raise KeyError(user_id)

    def delete_user(self, user_id: str) -> None:
        with self.connect() as db:
            row = db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                raise KeyError(user_id)
            if row["role"] == "admin":
                admin_count = db.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE role='admin'"
                ).fetchone()["c"]
                if admin_count <= 1:
                    raise ValueError("至少需要保留一个管理员")
            db.execute("DELETE FROM users WHERE id=?", (user_id,))  # FK 级联清 Session/消息/令牌

    def has_admin(self) -> bool:
        with self.connect() as db:
            return db.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role='admin'"
            ).fetchone()["c"] > 0

    # ---- Provider / Model 注册表（管理面维护，激活后覆盖 .env 模型配置） ----

    def list_providers(self) -> list[dict]:
        with self.connect() as db:
            providers = db.execute(
                "SELECT * FROM providers ORDER BY created_at"
            ).fetchall()
            models = db.execute(
                "SELECT * FROM provider_models ORDER BY created_at"
            ).fetchall()
        by_pid: dict[str, list[dict]] = {}
        for m in models:
            by_pid.setdefault(m["provider_id"], []).append(
                {"id": m["id"], "name": m["name"], "vision": bool(m["vision"])}
            )
        return [
            {
                "id": p["id"], "name": p["name"], "base_url": p["base_url"],
                "api_key": p["api_key"], "proxy": p["proxy"],
                "created_at": p["created_at"],
                "models": by_pid.get(p["id"], []),
            }
            for p in providers
        ]

    def create_provider(
        self, name: str, base_url: str, api_key: str, proxy: str | None = None
    ) -> dict:
        name = name.strip()
        if not name or not base_url.strip() or not api_key.strip():
            raise ValueError("名称、base_url、api_key 均不能为空")
        pid = f"prv_{uuid.uuid4().hex}"
        try:
            with self.connect() as db:
                db.execute(
                    "INSERT INTO providers VALUES (?,?,?,?,?,?)",
                    (pid, name, base_url.strip(), api_key.strip(),
                     (proxy or "").strip() or None, _now()),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Provider 名称已存在") from exc
        return {"id": pid, "name": name}

    def update_provider(self, provider_id: str, **fields) -> None:
        allowed = {"name", "base_url", "api_key", "proxy"}
        updates = {
            k: (v.strip() if isinstance(v, str) else v)
            for k, v in fields.items() if k in allowed
        }
        if not updates:
            return
        clause = ",".join(f"{k}=?" for k in updates)
        with self.connect() as db:
            result = db.execute(
                f"UPDATE providers SET {clause} WHERE id=?",
                (*updates.values(), provider_id),
            )
        if not result.rowcount:
            raise KeyError(provider_id)

    def delete_provider(self, provider_id: str) -> None:
        with self.connect() as db:
            model_ids = [
                row["id"]
                for row in db.execute(
                    "SELECT id FROM provider_models WHERE provider_id=?", (provider_id,)
                ).fetchall()
            ]
            result = db.execute("DELETE FROM providers WHERE id=?", (provider_id,))
            if not result.rowcount:
                raise KeyError(provider_id)
            self._drop_model_references(db, model_ids)
            # 激活模型随级联消失时清掉激活指针
            row = db.execute(
                "SELECT value FROM app_config WHERE key='ACTIVE_MODEL_ID'"
            ).fetchone()
            if row and db.execute(
                "SELECT id FROM provider_models WHERE id=?", (row["value"],)
            ).fetchone() is None:
                db.execute("DELETE FROM app_config WHERE key='ACTIVE_MODEL_ID'")

    @staticmethod
    def _drop_model_references(db, model_ids: list[str]) -> None:
        """模型被删除时，同步清掉用户偏好与会话覆盖里的悬空引用。"""
        for mid in model_ids:
            db.execute(
                "UPDATE user_model_prefs SET main_model_id=NULL WHERE main_model_id=?",
                (mid,),
            )
            db.execute(
                "UPDATE user_model_prefs SET sub_model_id=NULL WHERE sub_model_id=?",
                (mid,),
            )
            db.execute(
                "UPDATE user_model_prefs SET vision_model_id=NULL WHERE vision_model_id=?",
                (mid,),
            )
            db.execute(
                "UPDATE agent_sessions SET model_override_id=NULL "
                "WHERE model_override_id=?",
                (mid,),
            )

    def add_model(self, provider_id: str, name: str, vision: bool = False) -> dict:
        name = name.strip()
        if not name:
            raise ValueError("模型名不能为空")
        mid = f"mdl_{uuid.uuid4().hex}"
        try:
            with self.connect() as db:
                db.execute(
                    "INSERT INTO provider_models VALUES (?,?,?,?,?)",
                    (mid, provider_id, name, 1 if vision else 0, _now()),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("该 Provider 下模型已存在") from exc
        return {"id": mid, "name": name, "vision": bool(vision)}

    def update_model(self, model_id: str, **fields) -> None:
        updates: dict = {}
        if "name" in fields and str(fields["name"]).strip():
            updates["name"] = str(fields["name"]).strip()
        if "vision" in fields:
            updates["vision"] = 1 if fields["vision"] else 0
        if not updates:
            return
        clause = ",".join(f"{k}=?" for k in updates)
        with self.connect() as db:
            result = db.execute(
                f"UPDATE provider_models SET {clause} WHERE id=?",
                (*updates.values(), model_id),
            )
        if not result.rowcount:
            raise KeyError(model_id)

    def delete_model(self, model_id: str) -> None:
        with self.connect() as db:
            result = db.execute("DELETE FROM provider_models WHERE id=?", (model_id,))
            if not result.rowcount:
                raise KeyError(model_id)
            db.execute(
                "DELETE FROM app_config WHERE key='ACTIVE_MODEL_ID' AND value=?",
                (model_id,),
            )
            self._drop_model_references(db, [model_id])

    def set_active_model(self, model_id: str | None) -> None:
        with self.connect() as db:
            if model_id is None:
                db.execute("DELETE FROM app_config WHERE key='ACTIVE_MODEL_ID'")
                return
            if db.execute(
                "SELECT id FROM provider_models WHERE id=?", (model_id,)
            ).fetchone() is None:
                raise KeyError(model_id)
            db.execute(
                "INSERT OR REPLACE INTO app_config VALUES ('ACTIVE_MODEL_ID', ?, ?)",
                (model_id, _now()),
            )

    def active_model(self) -> dict | None:
        with self.connect() as db:
            row = db.execute("""
              SELECT m.id AS model_id, m.name AS model, m.vision,
                     p.id AS provider_id, p.name AS provider,
                     p.base_url, p.api_key, p.proxy
              FROM app_config c
              JOIN provider_models m ON m.id = c.value
              JOIN providers p ON p.id = m.provider_id
              WHERE c.key='ACTIVE_MODEL_ID'
            """).fetchone()
        return dict(row) if row else None

    def model_by_id(self, model_id: str) -> dict | None:
        """按 id 取模型（含 Provider 凭据），形状与 active_model 一致。"""
        with self.connect() as db:
            row = db.execute("""
              SELECT m.id AS model_id, m.name AS model, m.vision,
                     p.id AS provider_id, p.name AS provider,
                     p.base_url, p.api_key, p.proxy
              FROM provider_models m
              JOIN providers p ON p.id = m.provider_id
              WHERE m.id=?
            """, (model_id,)).fetchone()
        return dict(row) if row else None

    # ---- 用户模型偏好（角色级：主/子/视觉智能体）与会话级覆盖 ----

    @staticmethod
    def _empty_prefs() -> dict:
        return {
            "main_model_id": None, "sub_model_id": None, "vision_model_id": None,
        }

    def user_model_prefs(self, user_id: str) -> dict:
        with self.connect() as db:
            row = db.execute(
                "SELECT main_model_id, sub_model_id, vision_model_id "
                "FROM user_model_prefs WHERE user_id=?",
                (user_id,),
            ).fetchone()
        if row is None:
            return self._empty_prefs()
        return {
            "main_model_id": row["main_model_id"],
            "sub_model_id": row["sub_model_id"],
            "vision_model_id": row["vision_model_id"],
        }

    def set_user_model_prefs(
        self,
        user_id: str,
        main_model_id: str | None = None,
        sub_model_id: str | None = None,
        vision_model_id: str | None = None,
    ) -> dict:
        """整体覆盖某用户的模型偏好；None = 跟随默认。视觉槽只接受视觉模型。"""
        for mid in (main_model_id, sub_model_id, vision_model_id):
            if mid is not None and self.model_by_id(mid) is None:
                raise KeyError(mid)
        if vision_model_id is not None:
            row = self.model_by_id(vision_model_id)
            if not row["vision"]:
                raise ValueError("视觉智能体只能选择具备视觉能力的模型")
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO user_model_prefs VALUES (?,?,?,?,?)",
                (user_id, main_model_id, sub_model_id, vision_model_id, _now()),
            )
        return self.user_model_prefs(user_id)

    def set_session_model_override(
        self, session_id: str, model_id: str | None
    ) -> None:
        """会话级主模型覆盖；None = 清除覆盖，回到用户偏好/全局默认。"""
        if model_id is not None and self.model_by_id(model_id) is None:
            raise KeyError(model_id)
        with self.connect() as db:
            result = db.execute(
                "UPDATE agent_sessions SET model_override_id=? WHERE id=?",
                (model_id, session_id),
            )
        if not result.rowcount:
            raise KeyError(session_id)

    def first_vision_model(self, prefer_provider: str | None = None) -> dict | None:
        """主模型无视觉时的 OCR/看图兜底：优先同 Provider 的视觉模型。"""
        with self.connect() as db:
            rows = db.execute("""
              SELECT m.name AS model, p.id AS provider_id,
                     p.base_url, p.api_key, p.proxy
              FROM provider_models m JOIN providers p ON p.id = m.provider_id
              WHERE m.vision=1 ORDER BY m.created_at
            """).fetchall()
        if not rows:
            return None
        for row in rows:
            if row["provider_id"] == prefer_provider:
                return dict(row)
        return dict(rows[0])

    def seed_providers_from_settings(self, settings) -> bool:
        """注册表为空时用 .env 生效配置播种：default Provider + 主/视觉模型。"""
        if self.list_providers():
            return False
        tm = settings.text_model
        pid = self.create_provider("default", tm.base_url, tm.api_key, tm.proxy)["id"]
        mid = self.add_model(pid, tm.name, settings.text_model_vision)["id"]
        vm = settings.vision_model
        if vm is not None:
            if vm.base_url != tm.base_url or vm.api_key != tm.api_key:
                pid_v = self.create_provider(
                    "default-vision", vm.base_url, vm.api_key, vm.proxy
                )["id"]
            else:
                pid_v = pid
            self.add_model(pid_v, vm.name, True)
        self.set_active_model(mid)
        return True

    def import_providers(self, doc: dict) -> dict:
        """粘贴 JSON 批量导入 Provider 与模型；同名 Provider 合并并更新凭据。"""
        created_p = merged_p = created_m = 0
        if not isinstance(doc, dict) or not isinstance(doc.get("providers"), list):
            raise ValueError("JSON 顶层必须是包含 providers 数组的对象")
        for p in doc["providers"]:
            name = str(p.get("name", "")).strip()
            if not name:
                raise ValueError("provider 缺少 name")
            existing = next(
                (x for x in self.list_providers() if x["name"].lower() == name.lower()),
                None,
            )
            if existing is not None:
                pid = existing["id"]
                merged_p += 1
                updates = {
                    k: p[k] for k in ("base_url", "api_key", "proxy")
                    if p.get(k) and str(p[k]).strip() and p[k] != "********"
                }
                if updates:
                    self.update_provider(pid, **updates)
            else:
                pid = self.create_provider(
                    name,
                    str(p.get("base_url", "")),
                    str(p.get("api_key", "")),
                    p.get("proxy"),
                )["id"]
                created_p += 1
            for m in p.get("models", []):
                mname = str(m.get("name", "")).strip()
                if not mname:
                    continue
                try:
                    self.add_model(pid, mname, bool(m.get("vision", False)))
                    created_m += 1
                except ValueError:
                    if "vision" in m:  # 已存在则更新视觉标记
                        row = next(
                            (x for x in self.list_providers() if x["id"] == pid), None
                        )
                        hit = next(
                            (x for x in (row["models"] if row else [])
                             if x["name"] == mname), None,
                        )
                        if hit:
                            self.update_model(hit["id"], vision=bool(m["vision"]))
        activated = None
        active = str(doc.get("active", "")).strip()
        if active:
            pname, _, mname = active.partition("/")
            for prov in self.list_providers():
                if prov["name"].lower() == pname.lower():
                    hit = next((x for x in prov["models"] if x["name"] == mname), None)
                    if hit:
                        self.set_active_model(hit["id"])
                        activated = active
                    break
        return {
            "providers_created": created_p, "providers_merged": merged_p,
            "models_created": created_m, "activated": activated,
        }

    # ---- Provider/Model 配置覆盖层（DB > .env，见 config.apply_overrides） ----

    def config(self) -> dict[str, str]:
        with self.connect() as db:
            rows = db.execute("SELECT key,value FROM app_config").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def set_config(self, updates: dict[str, str]) -> None:
        with self.connect() as db:
            for key, value in updates.items():
                db.execute(
                    "INSERT OR REPLACE INTO app_config VALUES (?,?,?)",
                    (key, value, _now()),
                )

    def issue_token(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        with self.connect() as db:
            db.execute("INSERT INTO auth_tokens VALUES (?, ?, ?)", (token_hash, user_id, expires))
        return token

    def user_for_token(self, token: str | None) -> dict | None:
        if not token:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as db:
            row = db.execute("""
              SELECT users.id, users.username, users.avatar, users.role FROM auth_tokens
              JOIN users ON users.id=auth_tokens.user_id
              WHERE token_hash=? AND expires_at>?
            """, (digest, _now())).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "username": row["username"], "role": row["role"],
            "avatar_url": "/v1/auth/avatar" if row["avatar"] is not None else None,
        }

    def user_avatar(self, user_id: str) -> tuple[bytes, str] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT avatar,avatar_mime FROM users WHERE id=?", (user_id,)
            ).fetchone()
        if not row or row["avatar"] is None:
            return None
        return bytes(row["avatar"]), row["avatar_mime"] or "application/octet-stream"

    def set_user_avatar(
        self, user_id: str, content: bytes | None, media_type: str | None = None
    ) -> None:
        with self.connect() as db:
            result = db.execute(
                "UPDATE users SET avatar=?,avatar_mime=? WHERE id=?",
                (content, media_type, user_id),
            )
        if not result.rowcount:
            raise KeyError(user_id)

    def revoke_token(self, token: str | None):
        if token:
            with self.connect() as db:
                db.execute("DELETE FROM auth_tokens WHERE token_hash=?", (
                    hashlib.sha256(token.encode()).hexdigest(),
                ))

    def save_session(self, session_id: str, user_id: str, title: str):
        now = _now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO agent_sessions(id,user_id,title,created_at,updated_at) "
                "VALUES (?,?,?,?,?)",
                (session_id, user_id, title, now, now),
            )

    def sessions(self, user_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM agent_sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def session(self, session_id: str, user_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM agent_sessions WHERE id=? AND user_id=?", (session_id, user_id)).fetchone()
        return dict(row) if row else None

    def session_by_id(self, session_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM agent_sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def rename_session(self, session_id: str, user_id: str, title: str):
        with self.connect() as db:
            result = db.execute("UPDATE agent_sessions SET title=?, updated_at=? WHERE id=? AND user_id=?",
                                (title.strip()[:80] or "未命名会话", _now(), session_id, user_id))
        if not result.rowcount:
            raise KeyError(session_id)

    def delete_session(self, session_id: str, user_id: str):
        with self.connect() as db:
            result = db.execute("DELETE FROM agent_sessions WHERE id=? AND user_id=?", (session_id, user_id))
        if not result.rowcount:
            raise KeyError(session_id)

    def add_message(self, session_id: str, role: str, content: str, attachments: str = "[]"):
        with self.connect() as db:
            db.execute("INSERT INTO messages(session_id,role,content,attachments,created_at) VALUES(?,?,?,?,?)",
                       (session_id, role, content, attachments, _now()))
            db.execute("UPDATE agent_sessions SET updated_at=? WHERE id=?", (_now(), session_id))

    def messages(self, session_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT id,role,content,attachments,created_at FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        return [dict(row) for row in rows]

    def add_tool_event(
        self, session_id: str, agent: str, name: str,
        arguments: str | None = None, result: str | None = None,
        run_id: str | None = None,
    ) -> int:
        """插入一条工具调用事件；返回事件 id（用于 started→completed 关联）。"""
        with self.connect() as db:
            cur = db.execute(
                "INSERT INTO tool_events(session_id,run_id,agent,name,arguments,result,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (session_id, run_id, agent, name, arguments, result, _now()),
            )
            return cur.lastrowid

    def complete_tool_event(self, event_id: int, result: str | None) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE tool_events SET result=? WHERE id=?", (result, event_id)
            )

    def tool_events(self, session_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,agent,name,arguments,result,created_at FROM tool_events "
                "WHERE session_id=? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_session_file(self, session_id: str, file_id: str, path: Path) -> None:
        """登记 file_id → 文件绝对路径，随 Session 持久化。"""
        with self.connect() as db:
            exists = db.execute(
                "SELECT 1 FROM agent_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if exists is None:
                return  # session 不在库中（测试桩场景），跳过持久化
            db.execute(
                "INSERT OR REPLACE INTO session_files(file_id,session_id,path,created_at) "
                "VALUES(?,?,?,?)",
                (file_id, session_id, path.as_posix(), _now()),
            )

    def session_files(self, session_id: str) -> dict[str, Path]:
        """恢复 file_id → Path 映射（重建 SessionState 时用）。失效路径自动剔除。"""
        mapping: dict[str, Path] = {}
        with self.connect() as db:
            rows = db.execute(
                "SELECT file_id,path FROM session_files WHERE session_id=? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        for row in rows:
            p = Path(row["path"])
            if p.is_file():
                mapping[row["file_id"]] = p
        return mapping

    def context_messages(self, session_id: str) -> tuple[str | None, list[dict]]:
        with self.connect() as db:
            session = db.execute(
                "SELECT context_summary,context_cutoff_id FROM agent_sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if session is None:
                raise KeyError(session_id)
            rows = db.execute(
                "SELECT id,role,content,attachments,created_at FROM messages "
                "WHERE session_id=? AND id>? ORDER BY id",
                (session_id, session["context_cutoff_id"] or 0),
            ).fetchall()
        return session["context_summary"], [dict(row) for row in rows]

    def save_context_summary(
        self, session_id: str, summary: str, retained_messages: int
    ) -> None:
        with self.connect() as db:
            ids = [
                row["id"] for row in db.execute(
                    "SELECT id FROM messages WHERE session_id=? ORDER BY id",
                    (session_id,),
                ).fetchall()
            ]
            cutoff = ids[-retained_messages - 1] if len(ids) > retained_messages else 0
            db.execute(
                "UPDATE agent_sessions SET context_summary=?,context_cutoff_id=?,updated_at=? "
                "WHERE id=?",
                (summary, cutoff, _now(), session_id),
            )

    def clear_context(self, session_id: str) -> None:
        """截断上下文恢复点：摘要置空、cutoff 推到最新消息（消息记录保留）。"""
        with self.connect() as db:
            db.execute(
                "UPDATE agent_sessions SET context_summary=NULL,"
                "context_cutoff_id=(SELECT COALESCE(MAX(id),0) FROM messages WHERE session_id=?),"
                "updated_at=? WHERE id=?",
                (session_id, _now(), session_id),
            )

    def resource_mounts(self, session_id: str) -> dict[str, set[str]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT kind,name FROM resource_mounts WHERE session_id=?",
                (session_id,),
            ).fetchall()
        result: dict[str, set[str]] = {"skills": set()}
        for row in rows:
            result.setdefault(row["kind"], set()).add(row["name"])
        return result

    def set_resource_mount(
        self, session_id: str, kind: str, name: str, mounted: bool
    ) -> None:
        with self.connect() as db:
            if mounted:
                db.execute(
                    "INSERT OR REPLACE INTO resource_mounts VALUES (?, ?, ?, ?)",
                    (session_id, kind, name, _now()),
                )
            else:
                db.execute(
                    "DELETE FROM resource_mounts WHERE session_id=? AND kind=? AND name=?",
                    (session_id, kind, name),
                )
