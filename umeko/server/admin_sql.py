"""Administrator diagnostics with a portable, single-table SQL subset."""
from __future__ import annotations

import logging
import re
import sqlite3
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StringConstraints

from ..host.database import DatabaseIntegrityError, DatabaseUnavailable
from ..host.storage import Store

logger = logging.getLogger(__name__)
MAX_ROWS = 200

# Exclude dedicated credential fields, capability links and file mappings.
READ_COLUMNS = {
    "users": "id username role kind created_at avatar_mime",
    "agent_sessions": "id user_id title created_at updated_at context_cutoff_id model_override_id purpose",
    "messages": "id session_id role content attachments created_at",
    "tool_events": "id session_id run_id agent name arguments result created_at",
    "providers": "id name created_at",
    "provider_models": "id provider_id name vision created_at max_concurrent_requests user_enabled",
    "user_model_prefs": "user_id main_model_id sub_model_id vision_model_id updated_at",
    "tool_dispatch": "name enabled",
    "agent_definitions": "id slug name enabled created_at updated_at",
    "default_skills": "name enabled updated_at",
    "service_tasks": "id user_id agent_id source context_id session_id run_id status created_at updated_at completed_at expires_at",
    "service_task_events": "id task_id type created_at",
    "service_task_artifacts": "id task_id name media_type size",
    "skill_file_approvals": "pack member md5 sha256 actor created_at approval_id",
    "skill_file_revocations": "pack member md5 sha256 actor created_at event_id",
}
INSERT_COLUMNS = {
    "messages": "session_id role content created_at",
    "tool_events": "session_id run_id agent name arguments result created_at",
}

_NAME = r"[a-z_][a-z0-9_]*"
_TABLE = rf"(?P<table>{_NAME})"
_COLUMNS = rf"{_NAME}(?:\s*,\s*{_NAME})*"
_PREDICATE = rf"{_NAME}(?:\s*(?:<=|>=|<>|!=|=|<|>)\s*\?|\s+LIKE\s+\?|\s+IS\s+(?:NOT\s+)?NULL)"
_WHERE = rf"\s+WHERE\s+(?P<where>{_PREDICATE}(?:\s+AND\s+{_PREDICATE})*)"
_SET = rf"{_NAME}\s*=\s*\?"
_PATTERNS = {
    "SELECT": rf"SELECT\s+(?P<columns>{_COLUMNS}|\*|COUNT\(\*\))\s+FROM\s+{_TABLE}"
              rf"(?:{_WHERE})?(?:\s+ORDER\s+BY\s+(?P<order>{_NAME})(?:\s+(?P<direction>ASC|DESC))?)?"
              r"(?:\s+LIMIT\s+(?P<limit>[1-9][0-9]{0,8}))?",
    "INSERT": rf"INSERT\s+INTO\s+{_TABLE}\s*\((?P<columns>{_COLUMNS})\)\s+VALUES\s*\((?P<values>\?(?:\s*,\s*\?)*)\)",
    "UPDATE": rf"UPDATE\s+{_TABLE}\s+SET\s+(?P<assignments>{_SET}(?:\s*,\s*{_SET})*){_WHERE}",
    "DELETE": rf"DELETE\s+FROM\s+{_TABLE}{_WHERE}",
}
_STATEMENTS = {operation: re.compile(pattern, re.I | re.ASCII) for operation, pattern in _PATTERNS.items()}

Scalar = Annotated[str, StringConstraints(strict=True, max_length=16384)] | StrictInt | StrictFloat | StrictBool | None


class DiagnosticSqlIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    sql: str = Field(min_length=1, max_length=4096)
    params: list[Scalar] = Field(default_factory=list, max_length=100)


class DiagnosticSqlOut(BaseModel):
    operation: Literal["SELECT", "INSERT", "UPDATE", "DELETE"]
    table: str
    rows: list[dict]
    affected_rows: int
    truncated: bool


class DiagnosticTable(BaseModel):
    columns: list[str]
    writable: bool
    insert_columns: list[str]
    update_columns: list[str]


class DiagnosticCatalog(BaseModel):
    backend: Literal["sqlite", "postgresql"]
    max_rows: int
    tables: dict[str, DiagnosticTable]


def _checked_sql(payload: DiagnosticSqlIn) -> tuple[str, str, str, int]:
    sql = payload.sql.strip().removesuffix(";").strip()
    operation = re.split(r"\s+", sql, maxsplit=1)[0].upper()
    pattern = _STATEMENTS.get(operation)
    match = pattern.fullmatch(sql) if pattern else None
    if match is None:
        raise HTTPException(400, "需要一条受支持的单表 SQL，值用 ? 绑定，UPDATE 和 DELETE 需要 WHERE")
    if sql.count("?") != len(payload.params):
        raise HTTPException(400, "params 数量须与 ? 占位符一致")

    parts = match.groupdict()
    table = parts["table"].lower()
    available = READ_COLUMNS.get(table)
    if available is None or (operation != "SELECT" and table not in INSERT_COLUMNS):
        raise HTTPException(403, "该表不支持请求的诊断操作")
    where = parts.get("where") or ""
    conditions = re.split(r"\s+AND\s+", where, flags=re.I | re.ASCII) if where else []
    referenced = {re.match(_NAME, item.lower()).group() for item in conditions}
    columns = (parts.get("columns") or "").lower()
    order = parts.get("order")
    if order:
        referenced.add(order.lower())
    if operation in {"INSERT", "UPDATE"}:
        allowed = set(INSERT_COLUMNS[table].split())
        if operation == "INSERT":
            fields = [col.strip() for col in columns.split(",")]
        else:
            allowed.remove("session_id")
            fields = [item.split("=")[0].strip().lower() for item in parts["assignments"].split(",")]
        if not set(fields) <= allowed:
            raise HTTPException(403, "该字段不对诊断写入开放")
        if table == "messages" and any(col == "role" and value not in {"user", "assistant"}
                                       for col, value in zip(fields, payload.params)):
            raise HTTPException(400, "消息角色只能是 user 或 assistant")
    elif columns and columns not in {"*", "count(*)"}:
        referenced.update(col.strip() for col in columns.split(","))
    if not referenced.issubset(available.split()):
        raise HTTPException(403, "该字段不对 SQL 诊断开放")

    limit = min(int(parts.get("limit") or MAX_ROWS), MAX_ROWS)
    if operation == "SELECT":
        if columns == "*":
            columns = ", ".join(available.split())
        elif columns == "count(*)":
            columns = "COUNT(*) AS count"
        sql = f"SELECT {columns} FROM {table}"
        if where:
            sql += f" WHERE {where}"
        if order:
            sql += f" ORDER BY {order} {parts['direction'] or 'ASC'}"
        sql += f" LIMIT {limit + 1}"
    return operation, table, sql, limit


def install_admin_sql(app: FastAPI, store: Store) -> None:
    path = "/admin/v1/diagnostics/sql"

    @app.get(path, tags=["diagnostics"])
    def sql_diagnostics_catalog(response: Response) -> DiagnosticCatalog:
        response.headers["Cache-Control"] = "no-store"
        tables = {}
        for table, columns in READ_COLUMNS.items():
            writable = INSERT_COLUMNS.get(table, "").split()
            tables[table] = DiagnosticTable(columns=columns.split(), writable=bool(writable), insert_columns=writable,
                                            update_columns=[col for col in writable if col != "session_id"])
        return DiagnosticCatalog(backend=store.backend, max_rows=MAX_ROWS, tables=tables)

    @app.post(path, tags=["diagnostics"], responses={
        400: {"description": "SQL 不受支持、参数不符或执行失败。"},
        403: {"description": "诊断操作不允许访问该表或字段。"},
        409: {"description": "约束冲突或写入超过行数上限，事务回滚。"},
        415: {"description": "请求必须使用 application/json。"},
        503: {"description": "无法连接数据库。"},
    })
    def execute_diagnostic_sql(payload: DiagnosticSqlIn, request: Request, response: Response) -> DiagnosticSqlOut:
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise HTTPException(415, "请求必须使用 application/json")
        operation, table, sql, limit = _checked_sql(payload)
        params = [int(value) if isinstance(value, bool) else value for value in payload.params]
        driver_errors = (sqlite3.Error, OverflowError)
        if store.backend == "postgresql":
            import psycopg
            driver_errors += (psycopg.Error,)
        try:
            with store.connect() as db:
                db.limit_diagnostic_query()
                if operation != "SELECT":
                    db.begin_write()
                cursor = db.execute(sql, params)
                if operation == "SELECT":
                    selected = cursor.fetchmany(limit + 1)
                    result = DiagnosticSqlOut(operation=operation, table=table,
                                              rows=[dict(row) for row in selected[:limit]], affected_rows=0,
                                              truncated=len(selected) > limit)
                else:
                    if cursor.rowcount > MAX_ROWS:
                        raise HTTPException(409, f"写入超过 {MAX_ROWS} 行，已回滚")
                    result = DiagnosticSqlOut(operation=operation, table=table, rows=[],
                                              affected_rows=cursor.rowcount, truncated=False)
        except DatabaseUnavailable as exc:
            raise HTTPException(503, "数据库暂不可用") from exc
        except DatabaseIntegrityError as exc:
            raise HTTPException(409, "违反数据库约束，已回滚") from exc
        except driver_errors as exc:
            raise HTTPException(400, "SQL 执行失败，请核对字段类型、参数和查询大小") from exc
        if operation != "SELECT":
            logger.info("Administrator SQL write: admin=%s operation=%s table=%s rows=%d",
                        request.state.admin["id"], operation, table, result.affected_rows)
        response.headers["Cache-Control"] = "no-store"
        return result
