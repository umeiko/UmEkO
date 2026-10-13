import asyncio
import io
import time
import zipfile

import httpx
import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
import pytest

from conftest import wait_task
from umeko.host.tasks import TaskService


def task_root(app, task_id):
    with app.state.store.connect() as db:
        row = db.execute("SELECT user_id,session_id FROM service_tasks WHERE id=?", (task_id,)).fetchone()
    return app.state.agent_service.data_root / "users" / row["user_id"] / "sessions" / row["session_id"]


@pytest.mark.parametrize("machine_app", ["", "/teams/docs/umeko"], indirect=True)
@pytest.mark.parametrize("auth_mode", ["required", "anonymous"])
def test_numbered_files_download_and_scope(machine_client, auth_mode):
    client, app, account, other = machine_client
    app.state.identity_store.set_auth_mode(auth_mode)
    headers = {"Authorization": "Bearer " + account["token"]} if auth_mode == "required" else {}
    base = app.state.agent_service.settings.base_path + "/agent/fixture/v1/tasks"
    submitted = client.post(base, headers=headers, json={"prompt": "file fixture"}).json()
    task_id = submitted["task_id"]
    assert task_id == submitted["id"] and submitted["agent_id"] == app.state.fixture_agent["id"]
    for _ in range(200):
        task = client.get(base + "/" + task_id, headers=headers).json()
        if task["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(.02)
    assert task["status"] == "completed", task
    root = task_root(app, task_id)
    nested = root / "generate/图集"
    (nested / "empty").mkdir(parents=True)
    (nested / "证据.txt").write_text("evidence", encoding="utf-8")
    (root / "client/private.txt").write_text("private", encoding="utf-8")
    listing_url = base + "/" + task_id + "/files"
    listing = client.get(listing_url, headers=headers).json()
    assert listing["ready"]
    assert {item["name"] for item in listing["files"]} == {"workspace", "attachments", "generate"}
    assert all("children" not in item for item in listing["files"])
    generate_id = next(item["file_id"] for item in listing["files"] if item["name"] == "generate")
    generated = client.get(listing_url, params={"directory_id": generate_id}, headers=headers).json()["files"]
    report_id = next(item["file_id"] for item in generated if item["name"] == "report.txt")
    folder_id = next(item["file_id"] for item in generated if item["name"] == "图集")
    assert {item["name"] for item in generated} == {"report.txt", "图集"}
    (root / "generate/aaa.txt").write_text("new", encoding="utf-8")
    changed = client.get(listing_url, params={"directory_id": generate_id}, headers=headers).json()["files"]
    assert next(item["file_id"] for item in changed if item["name"] == "report.txt") == report_id
    download = listing_url + f"/{report_id}/content"
    response = client.get(download, headers=headers)
    assert response.content == (root / "generate/report.txt").read_bytes()
    assert "attachment" in response.headers["content-disposition"]
    response = client.get(listing_url + f"/{folder_id}/content", headers=headers)
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read("图集/证据.txt") == b"evidence"
        assert "图集/empty/" in archive.namelist()
    other_headers = {"Authorization": "Bearer " + other["token"]}
    assert client.get(listing_url, headers=other_headers).status_code == 404
    assert client.get(download, headers=other_headers).status_code == 404
    app.state.agent_service.agent_registry.save({"slug": "foreign", "name": "Foreign", "description": "fixture"})
    assert client.get(listing_url.replace("/agent/fixture/", "/agent/foreign/"), headers=headers).status_code == 404
    assert client.get(download.replace("/agent/fixture/", "/agent/foreign/"), headers=headers).status_code == 404
    assert client.get(listing_url, params={"directory_id": report_id}, headers=headers).status_code == 400
    assert client.get(listing_url + "/999999/content", headers=headers).status_code == 404
    principal = app.state.identity_store.authenticate(account["token"]) if auth_mode == "required" else app.state.identity_store.anonymous_principal()
    principal = {**principal, "agent_id": app.state.fixture_agent["id"]}
    restarted = TaskService(app.state.agent_service, app.state.agent_service.settings)
    assert restarted.file_info(principal, task_id, report_id)["name"] == "report.txt"
    (root / "generate/report.txt").unlink()
    assert client.get(download, headers=headers).status_code == 404
    with app.state.store.connect() as db:
        db.execute("UPDATE service_tasks SET workspace_expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (task_id,))
    assert client.get(base + "/" + task_id, headers=headers).status_code == 200
    assert client.get(listing_url, headers=headers).status_code == 404
    assert client.get(listing_url + f"/{folder_id}/content", headers=headers).status_code == 404


@pytest.mark.parametrize("machine_app", ["", "/teams/docs/umeko"], indirect=True)
def test_official_mcp_file_tools_and_download_prefix(machine_server):
    base, app, account, other = machine_server
    async def check():
        headers = {"Authorization": "Bearer " + account["token"]}
        async with httpx2.AsyncClient(headers=headers, trust_env=False) as transport:
            async with Client(streamable_http_client(base + "/mcp", http_client=transport), cache=None) as client:
                tools = (await client.list_tools()).tools
                assert {"list_file", "download_file"} <= {tool.name for tool in tools}
                assert not {"list_models", "list_tasks"} & {tool.name for tool in tools}
                prompts = (await client.list_prompts()).prompts
                assert [prompt.name for prompt in prompts] == ["task_lifecycle"]
                guide = await client.get_prompt("task_lifecycle")
                text = guide.messages[0].content.text
                assert all(name in text for name in ["submit_task", "task_id", "get_task", "list_file", "download_file", "workspace_url", "expired"])
                submitted = (await client.call_tool("submit_task", {"prompt": "file tools"})).structured_content
                task_id = submitted["task_id"]
                for _ in range(200):
                    result = (await client.call_tool("get_task", {"task_id": task_id})).structured_content
                    if result["status"] in {"completed", "failed", "cancelled"}:
                        break
                    await asyncio.sleep(.02)
                assert result["status"] == "completed"
                roots = (await client.call_tool("list_file", {"task_id": task_id})).structured_content
                folder_id = next(item["file_id"] for item in roots["files"] if item["name"] == "generate")
                files = (await client.call_tool("list_file", {"task_id": task_id, "directory_id": folder_id})).structured_content
                file_id = files["files"][0]["file_id"]
                for selected, zip_expected in [(file_id, False), (folder_id, True)]:
                    result = (await client.call_tool("download_file", {"task_id": task_id, "file_id": selected})).structured_content
                    assert result["download_url"].startswith(base + f"/v1/tasks/{task_id}/files/")
                    async with httpx.AsyncClient(headers=headers, trust_env=False) as http:
                        content = await http.get(result["download_url"])
                        assert content.status_code == 200
                        if zip_expected:
                            with zipfile.ZipFile(io.BytesIO(content.content)) as archive:
                                assert b"file tools" in archive.read("generate/report.txt")
                        else:
                            assert "file tools" in content.text
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + other["token"]}, trust_env=False) as transport:
            async with Client(streamable_http_client(base + "/mcp", http_client=transport), cache=None) as client:
                assert (await client.call_tool("list_file", {"task_id": task_id})).is_error
                assert (await client.call_tool("download_file", {"task_id": task_id, "file_id": file_id})).is_error
    asyncio.run(check())


def test_links_cannot_be_listed_downloaded_or_zipped(machine_client, tmp_path):
    client, app, account, _ = machine_client
    headers = {"Authorization": "Bearer " + account["token"]}
    base = "/agent/fixture/v1/tasks"
    task_id = client.post(base, headers=headers, json={"prompt": "safe links"}).json()["id"]
    assert wait_task(client, task_id, account["token"])["status"] == "completed"
    root = task_root(app, task_id)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret outside session", encoding="utf-8")
    link = root / "generate/link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Host cannot create test symlinks")
    listing_url = base + "/" + task_id + "/files"
    roots = client.get(listing_url, headers=headers).json()["files"]
    folder_id = next(item["file_id"] for item in roots if item["name"] == "generate")
    children = client.get(listing_url, params={"directory_id": folder_id}, headers=headers).json()["files"]
    assert "link.txt" not in {item["name"] for item in children}
    assert client.get(listing_url + f"/{folder_id}/content", headers=headers).status_code == 404
    file_id = children[0]["file_id"]
    report = root / "generate/report.txt"
    report.unlink()
    report.symlink_to(outside)
    assert client.get(listing_url + f"/{file_id}/content", headers=headers).status_code == 404
