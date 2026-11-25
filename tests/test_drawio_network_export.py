"""Exercise the actual HTTPS renderer contract against an isolated server."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from io import BytesIO
from ipaddress import ip_address
import json
from pathlib import Path
import ssl
import threading
import time
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PIL import Image
import pytest

from test_drawio_skill import FLOW, PACK, app_for


def load_exporter():
    spec = importlib.util.spec_from_file_location("fixture_drawio_xml", PACK / "scripts/drawio_xml.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def render_service(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Isolated render fixture")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.KeyUsage(True, False, True, False, False, True, True, False, False), critical=True)
            .sign(key, hashes.SHA256()))
    ca, private = tmp_path / "fixture-ca.pem", tmp_path / "fixture-key.pem"
    ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "white").save(buffer, format="PNG")
    png = buffer.getvalue()
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg"><defs><clipPath id="clip"><rect width="2" height="2"/>'
           b'</clipPath></defs><foreignObject clip-path="url(#clip)"><div xmlns="http://www.w3.org/1999/xhtml">'
           b'Fixture</div></foreignObject></svg>')
    images = {"png": png, "svg": svg}
    visits = []
    release_slow_request = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            visits.append((self.path, payload, self.headers.get("Authorization")))
            fmt = payload["format"]
            status, media, body = 200, {"png": "image/png", "svg": "image/svg+xml"}[fmt], images[fmt]
            if self.path == "/unavailable":
                status, body = 503, b"private upstream diagnostic"
            elif self.path == "/invalid":
                status, body = 422, b"invalid request"
            elif self.path == "/redirect":
                status, body = 307, b""
            elif self.path == "/bogus":
                body = b"<svg xmlns='http://www.w3.org/2000/svg' onload='noop()'/>" if fmt == "svg" else b"bad png"
            elif self.path == "/login":
                media, body = "text/html", b"<html>Sign in</html>"
            elif self.path == "/slow":
                release_slow_request.wait(10)
                return
            self.send_response(status)
            if self.path == "/redirect":
                self.send_header("Location", "/followed")
            self.send_header("Content-Type", media)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ca, private)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("UMEKO_DRAWIO_RENDER_CA_FILE", str(ca))
    monkeypatch.setenv("UMEKO_DRAWIO_PATH", str(tmp_path / "uninstalled-drawio"))
    try:
        yield f"https://127.0.0.1:{server.server_port}", visits, images
    finally:
        release_slow_request.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_approved_skill_posts_final_xml_and_tries_the_next_endpoint(tmp_path, render_service, approve_skill_files):
    base, visits, images = render_service
    service = app_for(tmp_path).state.agent_service
    pack = "drawio-flowchart"
    config = service._skills_library_dir() / pack / "assets/config.json"
    value = json.loads(config.read_text(encoding="utf-8"))
    value.update(render_urls=[base + "/unavailable", base + "/render"], render_bg="#ffffff", scale=2.5)
    config.write_text(json.dumps(value), encoding="utf-8")
    approve_skill_files(service, pack)
    owner = service.store.create_user("fixture-render", "fixture-pass")
    session = service.create_session(user_id=owner["id"])
    try:
        service.update_client_resource(session.id, "skills", pack + ".md", mounted=True)
        tool = session.agent._skills["run_skill_script"].handler
        args = json.dumps({"xml": FLOW, "formats": ["png", "svg"]})
        override = tool(pack=pack, script="generate_drawio.py",
                        args=json.dumps({"xml": FLOW, "render_urls": [base + "/override"]}))
        assert "SCRIPT_ARGUMENT_INVALID" in override and not visits
        result = tool(pack=pack, script="generate_drawio.py", args=args)
        assert "generate/flowchart.png" in result and "generate/flowchart.svg" in result and "HTTP 503" in result
        assert base not in result and "private upstream diagnostic" not in result
        output = session.root / "generate"
        assert [(route, payload["format"]) for route, payload, _ in visits] == [
            ("/unavailable", "png"), ("/render", "png"), ("/unavailable", "svg"), ("/render", "svg")]
        for fmt, image in images.items():
            assert (output / f"flowchart.{fmt}").read_bytes() == image
        for _, payload, authorization in visits:
            assert authorization is None
            assert ET.fromstring(payload["xml"]).tag == "mxfile"
            assert payload["xml"] == (output / "flowchart.drawio").read_bytes().decode("utf-8")
            assert payload["scale"] == (2.5 if payload["format"] == "png" else 1)
            assert payload["bg"] == "#ffffff"
        # Tampering with the approved address list must stop before any network call.
        copy = session.root / "client/skills" / pack / "assets/config.json"
        copy.write_bytes(copy.read_bytes() + b"\n")
        refused = tool(pack=pack, script="generate_drawio.py", args=args)
        assert "MD5" in refused and len(visits) == 4
    finally:
        service.evict_session(session.id)


def test_bad_network_results_fall_back_locally_and_pdf_skips_network(tmp_path, render_service, monkeypatch):
    base, visits, _ = render_service
    exporter = load_exporter()
    source = tmp_path / "fixture.drawio"
    source.write_text(FLOW, encoding="utf-8")
    monkeypatch.setattr(exporter, "_renderer", lambda config: ("fixture-local", None))
    calls = []

    def local(command, **kwargs):
        fmt = command[command.index("--format") + 1]
        calls.append(fmt)
        Path(command[command.index("--output") + 1]).write_bytes(b"local fixture")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(exporter.subprocess, "run", local)
    config = {"render_urls": [base + "/redirect", base + "/invalid", base + "/login", base + "/bogus"]}
    files, exports, errors, warnings = exporter.export_diagram(source, tmp_path, ["png", "svg", "pdf"], config)
    assert files == ["fixture.png", "fixture.svg", "fixture.pdf"] and not errors
    assert calls == ["png", "svg", "pdf"] and all(entry["backend"] == "local" for entry in exports)
    assert [route for route, _, _ in visits] == ["/redirect", "/invalid", "/login", "/bogus"] * 2
    assert all(any(reason in w for w in warnings) for reason in ("HTTP 307", "HTTP 422", "Content-Type", "PNG", "活动属性"))
    assert not any(base in item for item in warnings)


def test_invalid_or_untrusted_network_cannot_replace_output(tmp_path, render_service, monkeypatch):
    base, visits, _ = render_service
    source = tmp_path / "fixture.drawio"
    source.write_text(FLOW, encoding="utf-8")
    stale = tmp_path / "fixture.png"
    stale.write_bytes(b"old preview")
    monkeypatch.delenv("UMEKO_DRAWIO_RENDER_CA_FILE")
    files, _, errors, warnings = load_exporter().export_diagram(source, tmp_path, ["png"], {
        "render_urls": ["http://renderer.example.test/render", base + "/render"],
    })
    assert not files and not visits and source.is_file() and not stale.exists()
    assert "TLS 证书校验失败" in errors[0]["message"] and "HTTPS" in warnings[0]


def test_slow_response_keeps_budget_for_next_endpoint(tmp_path, render_service, monkeypatch):
    base, visits, images = render_service
    source = tmp_path / "fixture.drawio"
    source.write_text(FLOW, encoding="utf-8")
    exporter = load_exporter()
    monkeypatch.setattr(exporter, "_EXPORT_SECONDS", 3)
    started = time.monotonic()
    files, exports, errors, warnings = exporter.export_diagram(source, tmp_path, ["png"], {
        "render_urls": [base + "/slow", base + "/render"],
    })
    assert time.monotonic() - started < 3
    assert files == ["fixture.png"] and not errors and exports[0]["backend"] == "network"
    assert (tmp_path / "fixture.png").read_bytes() == images["png"]
    assert [route for route, _, _ in visits] == ["/slow", "/render"] and "请求超时" in warnings[0]
