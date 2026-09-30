"""Portable, localhost-only deployment verification; run `python lab.py --help`."""
import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
PREFIX = "/doc-master/consistency/image-text"
VERSION = "1.28.3"


def runtime_default():
    hint = HERE / "runtime.local"
    if hint.is_file():
        stored = json.loads(hint.read_text(encoding="utf-8")).get(os.name)
        if stored and Path(stored).is_absolute():
            return Path(stored)
    tag = hashlib.sha256(str(PROJECT).encode()).hexdigest()[:8]
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
    return base / "UmekoProxyLab" / tag


def run(command, **kwargs):
    subprocess.run([str(arg) for arg in command], check=True, **kwargs)


def python_in(root):
    return root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def configure(root):
    from certificates import generate
    hint = HERE / "runtime.local"
    stored = json.loads(hint.read_text(encoding="utf-8")) if hint.exists() else {}
    stored[os.name] = str(root)
    hint.write_text(json.dumps(stored, indent=2), encoding="utf-8")
    generate(root / "certs")
    (root / "logs").mkdir(exist_ok=True)
    (root / "temp").mkdir(exist_ok=True)
    path = root.as_posix()
    # The outer server preserves the path; the inner server removes it exactly once.
    config = f'''worker_processes 1;
daemon off;
pid "{path}/nginx.pid";
error_log "{path}/logs/nginx-error.log" info;
events {{ worker_connections 128; }}
http {{
    log_format lab '$server_port $request_method $uri $status upstream=$upstream_addr';
    access_log "{path}/logs/nginx-access.log" lab;
    client_max_body_size 64m;
    client_body_temp_path "{path}/temp/client_body";
    proxy_temp_path "{path}/temp/proxy";
    fastcgi_temp_path "{path}/temp/fastcgi";
    uwsgi_temp_path "{path}/temp/uwsgi";
    scgi_temp_path "{path}/temp/scgi";
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 30s;
    server {{
        listen 127.0.0.1:18443 ssl;
        server_name localhost;
        ssl_certificate "{path}/certs/web-cert.pem";
        ssl_certificate_key "{path}/certs/web-key.pem";
        ssl_protocols TLSv1.2 TLSv1.3;
        location = {PREFIX} {{ return 308 https://localhost:18443{PREFIX}/; }}
        location {PREFIX}/ {{
            proxy_set_header Connection "";
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_pass http://127.0.0.1:18080;
        }}
        location / {{ return 404 "ALB simulator: no path rule matched\\n"; }}
    }}
    server {{
        listen 127.0.0.1:18080;
        server_name localhost;
        location = {PREFIX} {{ return 308 {PREFIX}/; }}
        location {PREFIX}/ {{
            proxy_set_header Connection "";
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
            proxy_pass http://127.0.0.1:18000/;
        }}
        location / {{ return 404 "NGINX: no project prefix\\n"; }}
    }}
}}
'''
    (root / "nginx.conf").write_text(config, encoding="utf-8")


def prepare(root, nginx):
    root.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv")
    if not python_in(root).is_file():
        if uv:
            run([uv, "venv", "--python", sys.executable, root / "venv"])
        else:
            run([sys.executable, "-m", "venv", root / "venv"])
    if uv:
        run([uv, "pip", "install", "--python", python_in(root), "-e", str(PROJECT) + "[server]",
             "cryptography", "psutil"])
    else:
        run([python_in(root), "-m", "pip", "install", "-e", str(PROJECT) + "[server]",
             "cryptography", "psutil"])
    if nginx:
        executable = Path(nginx).resolve()
    elif os.name == "nt":
        executable = root / "vendor" / f"nginx-{VERSION}" / "nginx.exe"
        if not executable.is_file():
            url = f"https://nginx.org/download/nginx-{VERSION}.zip"
            archive = root / f"nginx-{VERSION}.zip"
            print("Downloading", url, flush=True)
            with urllib.request.urlopen(url, timeout=45) as response:
                archive.write_bytes(response.read())
            vendor = root / "vendor"
            vendor.mkdir(exist_ok=True)
            with zipfile.ZipFile(archive) as package:
                for member in package.infolist():
                    target = (vendor / member.filename).resolve()
                    if not target.is_relative_to(vendor.resolve()):
                        raise RuntimeError("Unsafe archive path")
                package.extractall(vendor)
            (root / "download.json").write_text(json.dumps({
                "url": url, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()
            }, indent=2), encoding="utf-8")
    else:
        located = shutil.which("nginx")
        if not located:
            raise RuntimeError("Install nginx in WSL first, then pass --nginx /usr/sbin/nginx")
        executable = Path(located)
    if not executable.is_file():
        raise RuntimeError(f"NGINX executable missing: {executable}")
    (root / "settings.json").write_text(json.dumps({"nginx": str(executable)}), encoding="utf-8")
    run([python_in(root), HERE / "lab.py", "configure", "--runtime", root])
    print("Prepared runtime:", root)


def nginx_command(root):
    executable = json.loads((root / "settings.json").read_text(encoding="utf-8"))["nginx"]
    return [executable, "-p", root.as_posix() + "/", "-c", "nginx.conf"]


def live_process(record):
    import psutil
    try:
        process = psutil.Process(record["pid"])
        if abs(process.create_time() - record["created"]) < 0.1:
            return process
    except psutil.Error:
        pass
    return None


def start(root):
    import psutil
    state_file = root / "processes.json"
    if state_file.is_file():
        existing = json.loads(state_file.read_text())
        if any(live_process(record) for record in existing):
            raise RuntimeError("Lab processes are already running; use status or stop first")
    for port in (18000, 18080, 18443, 19443):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    run(nginx_command(root) + ["-t"])
    env = dict(os.environ, UMEKO_LAB_RUNTIME=str(root), PYTHONIOENCODING="utf-8",
               UMEKO_BASE_PATH=PREFIX, MODEL_CA_FILE=str(root / "certs/model-ca.pem"))
    commands = [
        ("fake-model", [python_in(root), HERE / "mock_model.py", "--runtime", root]),
        ("umeko", [python_in(root), "-m", "uvicorn", "scripts.proxy_lab.app:create_lab_app", "--factory",
                   "--host", "127.0.0.1", "--port", "18000", "--root-path", PREFIX]),
        ("nginx", nginx_command(root)),
    ]
    records = []
    try:
        for name, command in commands:
            with (root / "logs" / f"{name}.log").open("ab") as log:
                child = subprocess.Popen([str(arg) for arg in command], cwd=PROJECT, env=env,
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            process = psutil.Process(child.pid)
            records.append({"name": name, "pid": child.pid, "created": process.create_time()})
            state_file.write_text(json.dumps(records, indent=2), encoding="utf-8")
        import httpx
        deadline = time.monotonic() + 20
        with httpx.Client(trust_env=False, timeout=1) as client:
            while time.monotonic() < deadline:
                if any(live_process(record) is None for record in records):
                    raise RuntimeError("A lab process exited; inspect the runtime logs")
                try:
                    if client.get("http://127.0.0.1:18080" + PREFIX + "/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Lab startup timed out")
    except Exception:
        stop(root)
        raise
    print("HTTPS edge: https://localhost:18443" + PREFIX + "/")
    print("HTTP inner: http://localhost:18080" + PREFIX + "/")
    print("Runtime prefix + explicit model CA configured; run verify to check the production agent.")
    print("Runtime:", root)


def stop(root):
    import psutil
    state_file = root / "processes.json"
    if not state_file.is_file():
        print("No lab process state")
        return
    records = json.loads(state_file.read_text())
    targets = []
    for record in records:
        process = live_process(record)
        if process:
            targets.append(process)
            # Only children of a positively identified lab-owned process.
            targets.extend(process.children(recursive=True))
    if any(record["name"] == "nginx" and live_process(record) for record in records):
        subprocess.run(nginx_command(root) + ["-s", "quit"], check=False, capture_output=True)
    for process in targets:
        try:
            process.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(targets, timeout=3)
    for process in alive:
        try:
            process.kill()
        except psutil.Error:
            pass
    state_file.write_text("[]", encoding="utf-8")
    print("Stopped lab-owned processes; certificates and reports retained.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "configure", "start", "verify", "status", "stop"))
    parser.add_argument("--runtime", type=Path, default=runtime_default())
    parser.add_argument("--nginx", help="Existing nginx executable, e.g. /usr/sbin/nginx in WSL")
    args = parser.parse_args()
    root = args.runtime.resolve()
    if args.action == "prepare":
        prepare(root, args.nginx)
        return
    lab_python = python_in(root)
    if not lab_python.is_file():
        raise RuntimeError("Run prepare first")
    if Path(sys.executable).resolve() != lab_python.resolve():
        # Keep the selected directory stable across Windows app path redirection.
        run([lab_python, HERE / "lab.py", *sys.argv[1:], "--runtime", root])
        return
    if args.action == "configure":
        configure(root)
    elif args.action == "start":
        start(root)
    elif args.action == "stop":
        stop(root)
    elif args.action == "verify":
        run([lab_python, HERE / "verify.py"], cwd=PROJECT,
            env=dict(os.environ, UMEKO_LAB_RUNTIME=str(root), PYTHONIOENCODING="utf-8"))
    elif args.action == "status":
        records = json.loads((root / "processes.json").read_text()) if (root / "processes.json").exists() else []
        print(json.dumps({"runtime": str(root), "processes": [
            dict(record, running=live_process(record) is not None) for record in records]}, indent=2))


if __name__ == "__main__":
    main()
