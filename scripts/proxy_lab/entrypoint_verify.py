"""Smoke the formal server entry and CLI REPL using only the isolated fake Provider."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(os.environ["UMEKO_LAB_RUNTIME"])
PREFIX = os.environ["UMEKO_BASE_PATH"]
ARGS = ["--env", str(ROOT / "lab.env"), "--data-root", str(ROOT / "data")]


def main():
    process = subprocess.Popen([sys.executable, "-m", "umeko.server", *ARGS,
        "--no-admin", "--host", "127.0.0.1", "--port", "18002"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url="http://127.0.0.1:18002", trust_env=False, timeout=2) as client:
            for _ in range(30):
                if process.poll() is not None:
                    raise AssertionError("Formal server entry exited")
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Formal server entry did not become ready")
            html = client.get("/").text
            assert f'content="{PREFIX}"' in html and PREFIX + "/static/ui/assets/" in html
            assert client.get("/v1/models").status_code == 401
            response = client.post("/v1/auth/register", json={"username":"entry_" + str(time.time_ns()), "password":"local-test-only"})
            response.raise_for_status()
            # Internal requests intentionally bypass NGINX here, so send the public-path cookie explicitly.
            token = next(cookie.value for cookie in client.cookies.jar if cookie.name == "umeko_auth")
            models = client.get("/v1/models", headers={"Cookie":"umeko_auth=" + token}).json()
            assert models["active_model_id"] and any(p["name"] == "lab" for p in models["providers"])
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    result = subprocess.run([sys.executable, "-m", "umeko.cli", *ARGS],
        input="Reply with LOCAL_MODEL_OK.\n/quit\n", text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, "CLI entry failed"
    assert "LOCAL_MODEL_OK" in result.stdout, "CLI did not receive fake model response"
    report = {"formal_server_entry": "ok", "shared_provider_registry": "ok", "cli_real_model_turn": "LOCAL_MODEL_OK", "scope":"fake model only"}
    (ROOT / "entrypoint-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
