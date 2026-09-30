"""Generate private lab CAs, two deployment proxies, and a root-path comparison."""
import json
import os
import sys
from pathlib import Path

from certificates import generate

PREFIX = "/doc-master/consistency/image-text"
ROOT = Path(os.environ.get("UMEKO_LAB_RUNTIME", "/runtime"))


def initialize():
    ROOT.mkdir(parents=True, exist_ok=True)
    generate(ROOT / "certs", hosts=("edge", "model"))
    common = '''worker_processes 1;
daemon off;
pid /tmp/umeko-lab-nginx.pid;
error_log /dev/stderr info;
events { worker_connections 128; }
http {
    log_format lab '$server_port $request_method $uri $status upstream=$upstream_addr';
    access_log /dev/stdout lab;
    client_max_body_size 64m;
    client_body_temp_path /tmp/umeko-lab-client-body;
    proxy_temp_path /tmp/umeko-lab-proxy;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 30s;
    absolute_redirect off;
'''
    headers = '''            proxy_set_header Connection "";
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
'''
    edge = common + f'''    server {{
        listen 18443 ssl;
        server_name localhost edge;
        ssl_certificate /runtime/certs/web-cert.pem;
        ssl_certificate_key /runtime/certs/web-key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        location = {PREFIX} {{ return 308 {PREFIX}/; }}
        location {PREFIX}/ {{
{headers}            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_pass http://web-proxy:18080;
        }}
        location / {{ return 404 "ALB simulator: no path rule matched\\n"; }}
    }}
}}
'''
    inner = common + f'''    server {{
        listen 18080;
        server_name localhost web-proxy;
        location = {PREFIX} {{ return 308 {PREFIX}/; }}
        location {PREFIX}/ {{
{headers}            proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
            proxy_pass http://app:18000/;
        }}
        location / {{ return 404 "NGINX: no project prefix\\n"; }}
    }}
}}
'''
    (ROOT / "edge.conf").write_text(edge)
    (ROOT / "inner.conf").write_text(inner)
    baseline = common + f'''    server {{
        listen 18081;
        server_name localhost baseline;
        location / {{
{headers}            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_pass http://root-app:18000;
        }}
    }}
}}
'''
    (ROOT / "baseline.conf").write_text(baseline)
    print("Initialized two independent CAs, two deployment proxies, and the root-path comparison.")


def health(kind):
    import urllib.request
    if kind == "app":
        url, context = "http://127.0.0.1:18000/health", None
    elif kind == "web-proxy":
        url, context = "http://127.0.0.1:18080" + PREFIX + "/health", None
    elif kind == "baseline":
        url, context = "http://127.0.0.1:18081/health", None
    else:
        import ssl
        if kind == "model":
            url, ca = "https://localhost:19443/health", "model"
        else:
            url, ca = "https://localhost:18443" + PREFIX + "/health", "web"
        context = ssl.create_default_context(cafile=ROOT / f"certs/{ca}-ca.pem")
    # No ambient proxy variables are used for these container-local health probes.
    handlers = [urllib.request.ProxyHandler({})]
    if context:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    with urllib.request.build_opener(*handlers).open(url, timeout=2) as response:
        assert response.status == 200


if __name__ == "__main__":
    if sys.argv[1] == "init":
        initialize()
    elif sys.argv[1] == "health":
        health(sys.argv[2])
    elif sys.argv[1] == "report":
        print((ROOT / "report.json").read_text())
