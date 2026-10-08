"""Acceptance: runtime prefix, real agent streaming, and strict model CA trust."""
import json
import os
import re
import socket
import ssl
import sys
import time
import uuid
from datetime import datetime, timezone
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path

import httpx
from openai import APIConnectionError

from umeko.config import ModelConfig
from umeko.llm.client import LLMClient

PREFIX = "/doc-master/consistency/image-text"
ROOT = Path(os.environ["UMEKO_LAB_RUNTIME"])
BASE = os.environ.get("UMEKO_LAB_BASE_URL", "https://localhost:18443")
RESULTS = []


def record(name, **evidence):
    RESULTS.append({"check": name, **evidence})
    print("PASS", name, json.dumps(evidence, ensure_ascii=True), flush=True)


def certificate_error(exc):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def read_events(client, run_id):
    started = time.monotonic()
    items, heartbeats, event_type, data = [], 0, "", ""
    with client.stream("GET", BASE + PREFIX + f"/v1/runs/{run_id}/events") as response:
        response.raise_for_status()
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith(":"):
                heartbeats += 1
            elif line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
            elif not line and data:
                items.append({"type": event_type, "at": round(time.monotonic() - started, 3),
                              "payload": json.loads(data)})
                data = ""
    return items, heartbeats


def main():
    web_ca = ROOT / "certs/web-ca.pem"
    model_ca = ROOT / "certs/model-ca.pem"
    model_url = os.environ.get("UMEKO_LAB_MODEL_URL", "https://localhost:19443/v1")
    if os.environ.get("UMEKO_LAB_DOCKER") == "1":
        record("container service DNS resolution", addresses={
            host: socket.gethostbyname(host) for host in ("edge", "web-proxy", "app", "model")})
    web_context = ssl.create_default_context(cafile=web_ca)
    with httpx.Client(verify=web_context, trust_env=False, timeout=30) as client:
        page = client.get(BASE + PREFIX + "/")
        page.raise_for_status()
        assert client.get(BASE + PREFIX + "/health").json() == {"status": "ok"}
        record("two proxy hops + trusted website HTTPS", status=page.status_code)
        resources = re.findall(r'(?:src|href)="([^"?]*/static/[^"?]+)', page.text)
        assert len(resources) >= 2
        for resource in sorted(set(resources)):
            assert resource.startswith(PREFIX + "/static/")
            outside = client.get(BASE + resource[len(PREFIX):])
            inside = client.get(BASE + resource)
            assert outside.status_code == 404 and inside.status_code == 200
        assert client.get(BASE + "/v1/auth/me").status_code == 404
        assert client.get(BASE + PREFIX + "/v1/auth/me").status_code == 401
        record("FIX verified: runtime-prefixed frontend assets",
               root_resource_status=404, prefixed_resource_status=200, resources=len(set(resources)))

        username = "lab_" + uuid.uuid4().hex[:10]
        auth = {"username": username, "password": "lab-test-only"}
        client.post(BASE + PREFIX + "/v1/auth/register", json=auth).raise_for_status()
        client.post(BASE + PREFIX + "/v1/auth/logout").raise_for_status()
        client.post(BASE + PREFIX + "/v1/auth/login", json=auth).raise_for_status()
        assert client.get(BASE + PREFIX + "/v1/auth/me").json()["username"] == username
        session_id = client.post(BASE + PREFIX + "/v1/sessions", json={}).json()["id"]
        record("prefixed registration + login + cookie + session", status="ok")

        uploaded = client.post(BASE + PREFIX + f"/v1/sessions/{session_id}/workspace/files",
                               params={"filename": "lab.txt"}, content=b"LOCAL_DOWNLOAD_OK")
        uploaded.raise_for_status()
        downloaded = client.get(BASE + PREFIX + f"/v1/sessions/{session_id}/workspace/files/download",
                                params={"path": uploaded.json()["path"]})
        assert downloaded.status_code == 200 and downloaded.content == b"LOCAL_DOWNLOAD_OK"
        record("prefixed upload + download", bytes=len(downloaded.content))

        fixture = client.post(BASE + PREFIX + f"/v1/__lab/sessions/{session_id}/stream-fixture")
        fixture.raise_for_status()
        items, heartbeats = read_events(client, fixture.json()["id"])
        deltas = [item for item in items if item["type"] == "assistant.delta"]
        assert len(deltas) == 3 and deltas[-1]["at"] - deltas[0]["at"] >= 0.35
        assert items[-1]["type"] == "run.completed" and heartbeats >= 1
        record("real Umeko SSE endpoint through both proxies (fixture, no model)",
               delta_seconds=[item["at"] for item in deltas], heartbeats=heartbeats)

        # Real production agent, configured via the shared Provider registry + explicit model CA.
        run_response = client.post(BASE + PREFIX + f"/v1/sessions/{session_id}/runs",
                                   json={"input": "Reply with LOCAL_MODEL_OK."})
        run_response.raise_for_status()
        completed, _ = read_events(client, run_response.json()["id"])
        assert completed[-1]["type"] == "run.completed", completed[-1]
        assert completed[-1]["payload"]["data"]["reply"] == "LOCAL_MODEL_OK"
        deltas = [item for item in completed if item["type"] == "assistant.delta"]
        assert len(deltas) == 3 and deltas[-1]["at"] - deltas[0]["at"] >= 0.5
        record("FIX verified: production agent + Provider registry + model CA + proxied streaming",
               terminal=completed[-1]["type"], delta_seconds=[item["at"] for item in deltas])

    previous = os.environ.get("SSL_CERT_FILE")
    os.environ["SSL_CERT_FILE"] = str(model_ca)
    sdk = LLMClient(ModelConfig("lab-model", "local-test-only", model_url))._get_client()
    try:
        with sdk.with_options(max_retries=0, timeout=5) as probe:
            reply = probe.chat.completions.create(model="lab-model", messages=[{"role": "user", "content": "test"}])
        assert reply.choices[0].message.content == "LOCAL_MODEL_OK"
        record("current SDK with SSL_CERT_FILE: model CA accepted on this platform",
               reply=reply.choices[0].message.content,
               transport=type(sdk._client).__module__)
    except APIConnectionError as exc:
        assert certificate_error(exc), repr(exc)
        record("current SDK with SSL_CERT_FILE: model CA rejected on this platform",
               cause="CERTIFICATE_VERIFY_FAILED")
    finally:
        sdk.close()
    try:
        with httpx.Client(trust_env=False, timeout=5) as old_transport:
            old_transport.get(model_url + "/health")
        raise AssertionError("HTTPX trust_env=False should ignore SSL_CERT_FILE")
    except httpx.ConnectError as exc:
        assert certificate_error(exc)
        record("control: HTTPX trust_env=False ignores SSL_CERT_FILE",
               httpx_version=version("httpx"), cause="CERTIFICATE_VERIFY_FAILED")
    finally:
        if previous is None:
            os.environ.pop("SSL_CERT_FILE", None)
        else:
            os.environ["SSL_CERT_FILE"] = previous

    try:
        with httpx.Client(verify=web_context, trust_env=False) as wrong_trust:
            wrong_trust.get(model_url + "/health")
        raise AssertionError("Website CA must not authenticate the model server")
    except httpx.ConnectError as exc:
        assert certificate_error(exc)
        record("website CA and model CA are independent")

    # Exercise the actual modified client too: a wrong custom CA must still fail.
    wrong_sdk = LLMClient(ModelConfig("lab-model", "local-test-only", model_url, ca_file=str(web_ca)))._get_client()
    try:
        wrong_sdk.with_options(max_retries=0, timeout=5).chat.completions.create(
            model="lab-model", messages=[{"role": "user", "content": "test"}])
        raise AssertionError("Wrong model CA was accepted by the production client")
    except APIConnectionError as exc:
        assert certificate_error(exc)
        record("negative control: production client rejects wrong MODEL_CA_FILE")
    finally:
        wrong_sdk.close()

    with LLMClient(ModelConfig("lab-model", "local-test-only", model_url, ca_file=str(model_ca)))._get_client().with_options(max_retries=0) as trusted:
        started, pieces, times = time.monotonic(), [], []
        stream = trusted.chat.completions.create(model="lab-model", stream=True,
                         messages=[{"role": "user", "content": "test"}])
        with stream:
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    pieces.append(chunk.choices[0].delta.content)
                    times.append(round(time.monotonic() - started, 3))
        assert "".join(pieces) == "LOCAL_MODEL_OK" and times[-1] - times[0] >= 0.5
        record("positive control: explicit model CA + SDK model streaming", delta_seconds=times)

    report = {"scope": "fix acceptance; actual UmEkO frontend/agent/config; fake model only",
              "verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "python": sys.version,
              "dependencies": {name: version(name) for name in ("openai", "httpx", "httpx2", "truststore", "fastapi")
                               if find_spec(name)},
              "url": BASE + PREFIX + "/", "results": RESULTS}
    if Path("/etc/os-release").is_file():
        report["os_release"] = Path("/etc/os-release").read_text()
    (ROOT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPORT", ROOT / "report.json")


if __name__ == "__main__":
    main()
