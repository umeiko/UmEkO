"""Read-only admin inspection of persisted records; never wake an agent session."""
from __future__ import annotations

import json
from ..host.file_manifest import capture, recorded_files, session_root, MAX_ENTRIES


def _session(db, session_id):
    row = db.execute(
        "SELECT s.id,s.user_id,s.title,s.purpose,s.created_at,s.updated_at,"
        "s.context_summary,s.context_cutoff_id,u.username FROM agent_sessions s "
        "JOIN users u ON u.id=s.user_id WHERE s.id=?", (session_id,),
    ).fetchone()
    if row is None:
        return None
    record = dict(row)
    cutoff = record.pop("context_cutoff_id") or 0
    summary = record.pop("context_summary")
    messages = []
    for message in db.execute(
        "SELECT id,role,content,attachments,created_at FROM messages "
        "WHERE session_id=? ORDER BY id", (session_id,),
    ):
        item = dict(message)
        try:
            attachments = json.loads(item["attachments"])
        except (ValueError, TypeError):
            attachments = []
        item["attachments"] = attachments if isinstance(attachments, list) else []
        item["in_context"] = item["id"] > cutoff
        messages.append(item)
    skills = [r["name"] for r in db.execute(
        "SELECT name FROM resource_mounts WHERE session_id=? AND kind='skills' ORDER BY name",
        (session_id,),
    )]
    return {"record": record, "messages": messages,
            "context": {"summary": summary, "cutoff_id": cutoff,
                        "skill_names": skills, "session_available": True}}


def _tools(db, session_id, run_id=None):
    query = ("SELECT id,run_id,agent,name,arguments,result,created_at FROM tool_events "
             "WHERE session_id=?")
    args = [session_id]
    if run_id is not None:
        query += " AND (run_id=? OR run_id IS NULL)"
        args.append(run_id)
    return [dict(row) for row in db.execute(query + " ORDER BY id", args)]


def session_detail(service, session_id):
    with service.store.connect() as db:
        db.execute("BEGIN")
        detail = _session(db, session_id)
        if detail is None:
            raise KeyError("会话不存在")
        detail["tools"] = _tools(db, session_id)
    detail["record"]["loaded"] = session_id in service.sessions
    return {"kind": "session", **detail}


def task_detail(service, task_id):
    with service.store.connect() as db:
        db.execute("BEGIN")
        row = db.execute(
            "SELECT t.*,COALESCE(g.name,'历史入口') AS agent_name,"
            "CASE WHEN u.kind='anonymous' THEN '免鉴权调用' "
            "ELSE COALESCE(a.name,u.username) END AS caller FROM service_tasks t "
            "JOIN users u ON u.id=t.user_id LEFT JOIN service_accounts a ON a.user_id=t.user_id "
            "LEFT JOIN agent_definitions g ON g.id=t.agent_id WHERE t.id=?", (task_id,),
        ).fetchone()
        if row is None:
            raise KeyError("任务不存在")
        payload = json.loads(row["input_json"])
        session = _session(db, row["session_id"]) if row["session_id"] else None
        context = (session["context"] if session else
                   {"summary": None, "cutoff_id": 0, "skill_names": [], "session_available": False})
        # Keep the submitted configuration, rather than substituting today's agent settings.
        snapshot = payload.get("agent_snapshot")
        context["agent_snapshot"] = ({key: snapshot[key] for key in (
            "id", "slug", "name", "description", "version", "system_prompt", "default_model_id",
            "default_vision_model_id", "disclosed_model_ids", "skill_names", "dispatched_skills",
        ) if key in snapshot} if isinstance(snapshot, dict) else None)
        artifacts = [dict(r) for r in db.execute(
            "SELECT id,name,media_type,size FROM service_task_artifacts WHERE task_id=?", (task_id,),
        )]
        events = [{**dict(r), "data": json.loads(r["data"])} for r in db.execute(
            "SELECT id,type,data,created_at FROM service_task_events WHERE task_id=? ORDER BY id",
            (task_id,),
        )]
        return {
            "kind": "task",
            "record": {key: row[key] for key in (
                "id", "user_id", "agent_id", "agent_name", "caller", "caller_ip", "source", "status",
                "context_id", "session_id", "run_id", "created_at", "updated_at", "completed_at", "expires_at",
            )},
            "input": {key: payload[key] for key in ("prompt", "model_id", "files", "message_id") if key in payload},
            "output": {"reply": row["reply"], "error": row["error"], "artifacts": artifacts},
            "messages": session["messages"] if session else [],
            "tools": _tools(db, row["session_id"], row["run_id"]) if row["run_id"] else [],
            "context": context, "events": events,
        }


def task_files(service, task_id):
    with service.store.connect() as db:
        row = db.execute("SELECT user_id,session_id,status,input_json,created_at,file_manifest_json "
                         "FROM service_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError("任务不存在")
        artifacts = [dict(item) for item in db.execute(
            "SELECT name,size FROM service_task_artifacts WHERE task_id=? ORDER BY name LIMIT ?", (task_id, MAX_ENTRIES))]
    if row["file_manifest_json"] and row["status"] in {"completed", "failed", "cancelled"}:
        return {**json.loads(row["file_manifest_json"]), "source": "snapshot"}
    if row["session_id"]:
        root = session_root(service.data_root, row["user_id"], row["session_id"])
        current = capture(root) if root is not None else None
        if current is not None:
            return {**current, "source": "current"}
    return {**recorded_files(json.loads(row["input_json"]), artifacts, row["created_at"]),
            "source": "records" if row["session_id"] else "submitted"}
