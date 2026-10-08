"""Machine identities and revocable credentials, shared by every protocol."""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from .storage import Store

SCOPES = frozenset({"tasks:create", "tasks:read", "tasks:cancel", "artifacts:read"})


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class IdentityStore:
    def __init__(self, store: Store):
        self.store = store
        with store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS service_accounts (
              id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
              user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
              enabled INTEGER NOT NULL DEFAULT 1, scopes TEXT NOT NULL,
              token_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
              expires_at TEXT NOT NULL, last_used_at TEXT
            );
            CREATE TABLE IF NOT EXISTS service_access_tokens (
              token_hash TEXT PRIMARY KEY,
              account_id TEXT NOT NULL REFERENCES service_accounts(id) ON DELETE CASCADE,
              resource TEXT NOT NULL, scopes TEXT NOT NULL, expires_at TEXT NOT NULL
            );
            """)

    @staticmethod
    def _view(row) -> dict:
        return {**{key: row[key] for key in (
            "id", "name", "user_id", "created_at", "expires_at", "last_used_at")},
                "enabled": bool(row["enabled"]), "scopes": json.loads(row["scopes"])}

    def list(self) -> list[dict]:
        with self.store.connect() as db:
            return [self._view(r) for r in db.execute("SELECT * FROM service_accounts ORDER BY created_at")]

    def auth_mode(self) -> str:
        return "anonymous" if self.store.config().get("SERVICE_AUTH_MODE") == "anonymous" else "required"

    def set_auth_mode(self, mode: str) -> None:
        if mode not in {"required", "anonymous"}:
            raise ValueError("接入方式须为 required 或 anonymous")
        self.store.set_config({"SERVICE_AUTH_MODE": mode})

    def anonymous_principal(self) -> dict:
        # A single persistent identity for open access; IP is never an ownership key.
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM users WHERE kind='anonymous' LIMIT 1").fetchone()
            if row:
                user_id = row["id"]
            else:
                user_id = "usr_" + uuid.uuid4().hex
                db.execute("INSERT INTO users(id,username,password_hash,created_at,role,kind) VALUES(?,?,?,?,?,?)",
                           (user_id, "anonymous-" + user_id, "!machine-only", now(), "user", "anonymous"))
        return {"id": "anonymous", "user_id": user_id, "name": "免鉴权调用", "scopes": sorted(SCOPES)}

    def create(self, name: str, scopes: list[str], expires_days: int = 90) -> dict:
        name = name.strip()
        if not 1 <= len(name) <= 80 or not scopes or not set(scopes) <= SCOPES:
            raise ValueError("名称须为 1–80 字符，权限须来自支持的任务权限")
        if not 1 <= expires_days <= 3650:
            raise ValueError("凭据有效期须为 1–3650 天")
        account_id, user_id = "svc_" + uuid.uuid4().hex, "usr_" + uuid.uuid4().hex
        token = "umeko_svc_" + secrets.token_urlsafe(36)
        created, expires = now(), (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
        try:
            with self.store.connect() as db:
                db.execute("INSERT INTO users(id,username,password_hash,created_at,role,kind) VALUES(?,?,?,?,?,?)",
                           (user_id, account_id, "!machine-only", created, "user", "service"))
                db.execute("INSERT INTO service_accounts(id,name,user_id,scopes,token_hash,created_at,expires_at) "
                           "VALUES(?,?,?,?,?,?,?)", (account_id, name, user_id, json.dumps(sorted(set(scopes))),
                                                    digest(token), created, expires))
        except sqlite3.IntegrityError as exc:
            raise ValueError("服务账号名称已存在") from exc
        return {**next(a for a in self.list() if a["id"] == account_id), "token": token}

    def update(self, account_id: str, *, enabled: bool | None = None, rotate: bool = False,
               expires_days: int = 90) -> dict:
        if not 1 <= expires_days <= 3650:
            raise ValueError("凭据有效期须为 1–3650 天")
        token = "umeko_svc_" + secrets.token_urlsafe(36) if rotate else None
        with self.store.connect() as db:
            if db.execute("SELECT 1 FROM service_accounts WHERE id=?", (account_id,)).fetchone() is None:
                raise KeyError("服务账号不存在")
            if enabled is not None:
                db.execute("UPDATE service_accounts SET enabled=? WHERE id=?", (int(enabled), account_id))
            if token:
                expires = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()
                db.execute("UPDATE service_accounts SET token_hash=?,expires_at=? WHERE id=?",
                           (digest(token), expires, account_id))
            if rotate or enabled is False:
                db.execute("DELETE FROM service_access_tokens WHERE account_id=?", (account_id,))
        view = next(a for a in self.list() if a["id"] == account_id)
        return {**view, **({"token": token} if token else {})}

    def authenticate(self, token: str | None, resource: str | None = None) -> dict | None:
        if not token or len(token) > 512:
            return None
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM service_accounts WHERE token_hash=? AND enabled=1 AND expires_at>?",
                             (digest(token), now())).fetchone()
            scopes = None
            if row is None:
                access = db.execute("SELECT * FROM service_access_tokens WHERE token_hash=? AND expires_at>?",
                                    (digest(token), now())).fetchone()
                if access is None or (resource is not None and access["resource"] != resource):
                    return None
                row = db.execute("SELECT * FROM service_accounts WHERE id=? AND enabled=1 AND expires_at>?",
                                 (access["account_id"], now())).fetchone()
                scopes = json.loads(access["scopes"])
            if row is None:
                return None
            db.execute("UPDATE service_accounts SET last_used_at=? WHERE id=?", (now(), row["id"]))
            view = self._view(row)
            if scopes is not None:
                view["scopes"] = scopes
            return view

    def issue_access_token(self, client_id: str, secret: str, resource: str, scopes: list[str]) -> dict:
        if not secret.startswith("umeko_svc_"):
            raise PermissionError("invalid_client")
        account = self.authenticate(secret)
        if not account or account["id"] != client_id:
            raise PermissionError("invalid_client")
        if not set(scopes) <= set(account["scopes"]):
            raise ValueError("invalid_scope")
        token = "umeko_access_" + secrets.token_urlsafe(36)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM service_accounts WHERE id=? AND token_hash=? AND enabled=1 AND expires_at>?",
                          (client_id, digest(secret), now())).fetchone() is None:
                raise PermissionError("invalid_client")
            db.execute("DELETE FROM service_access_tokens WHERE expires_at<=?", (now(),))
            db.execute("INSERT INTO service_access_tokens VALUES(?,?,?,?,?)",
                       (digest(token), client_id, resource, json.dumps(scopes),
                        (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()))
        return {"access_token": token, "token_type": "Bearer", "expires_in": 3600, "scope": " ".join(scopes)}


def require_scope(principal: dict, scope: str) -> str:
    if scope not in principal.get("scopes", []):
        raise PermissionError("调用凭据缺少权限：" + scope)
    return principal["user_id"]
