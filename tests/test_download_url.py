"""Real isolated HTTP transfers, exact size limits, cleanup and URL/path boundaries."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import socket
import ssl
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

from umeko.cancellation import OperationCancelled
from umeko.config import DownloadConfig
from umeko.skills import download


@pytest.fixture
def files(tmp_path, monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/redirect":
                self.send_response(302); self.send_header("Location", "/small.txt"); self.end_headers(); return
            if self.path == "/private":
                self.send_response(302); self.send_header("Location", "http://127.0.0.1/private"); self.end_headers(); return
            if self.path == "/missing":
                self.send_response(404); self.end_headers(); return
            self.send_response(200)
            if self.path == "/big-length":
                self.send_header("Content-Length", str(download.MAX_DOWNLOAD_BYTES + 1)); self.end_headers(); return
            if self.path == "/truncated":
                self.send_header("Content-Length", "100"); self.end_headers(); self.wfile.write(b"short"); return
            if self.path == "/name":
                self.send_header("Content-Disposition", 'attachment; filename="../../report.txt"')
            if self.path in {"/big-stream", "/exact"}:
                # No Content-Length: prove stream accounting, not just header checking.
                self.end_headers()
                size = download.MAX_DOWNLOAD_BYTES + (1 if self.path == "/big-stream" else 0)
                try:
                    while size:
                        chunk = b"x" * min(65536, size)
                        self.wfile.write(chunk); size -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            self.send_header("Content-Length", "7"); self.end_headers(); self.wfile.write(b"fixture")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    addresses = download._addresses
    # Only this controlled test hostname is pinned to the isolated fixture server.
    monkeypatch.setattr(download, "_addresses", lambda host, port, internal_hosts=():
                        ["127.0.0.1"] if host == "files.example.test" else addresses(host, port, internal_hosts))
    root = tmp_path / "session"
    (root / "workspace").mkdir(parents=True); (root / "generate").mkdir()
    def run(route, **kwargs):
        return download.download_url(f"http://files.example.test:{server.server_port}{route}", root=root,
            allowed_roots=(root / "workspace", root / "generate"), default_dir="workspace/downloads", **kwargs)
    yield run, root
    server.shutdown(); server.server_close(); thread.join(2)


def test_download_redirect_filename_and_no_implicit_overwrite(files):
    run, root = files
    result = json.loads(run("/redirect"))
    assert result["ok"] and result["path"] == "workspace/downloads/small.txt" and result["size"] == 7
    assert (root / result["path"]).read_bytes() == b"fixture"
    assert "目标已存在" in run("/redirect")
    named = json.loads(run("/name"))
    assert (root / named["path"]).parent == root / "workspace/downloads"
    assert (root / named["path"]).read_bytes() == b"fixture"
    explicit = json.loads(run("/small.txt", path="generate/result.bin"))
    assert explicit["path"] == "generate/result.bin"
    assert json.loads(run("/small.txt", path="generate/result.bin", overwrite=True))["ok"]


@pytest.mark.parametrize("route", ["/big-length", "/big-stream", "/truncated", "/missing", "/private"])
def test_failed_download_cleans_partial_files_and_preserves_previous(files, route):
    run, root = files
    existing = root / "generate/result.bin"; existing.write_bytes(b"previous")
    result = run(route, path="generate/result.bin", overwrite=True)
    assert result.startswith("错误：") and existing.read_bytes() == b"previous"
    assert not list(root.rglob(".download-*"))
    if route.startswith("/big"):
        assert "20 MB" in result
    assert str(root) not in result


def test_exact_limit_succeeds_and_cancellation_cleans_partial_download(files):
    run, root = files
    body = json.loads(run("/exact", path="generate/exact.bin"))
    assert body["size"] == download.MAX_DOWNLOAD_BYTES
    assert (root / body["path"]).stat().st_size == download.MAX_DOWNLOAD_BYTES
    calls = []
    def cancel():
        calls.append(1)
        return len(calls) > 4
    with pytest.raises(OperationCancelled):
        run("/exact", path="generate/cancelled.bin", should_cancel=cancel)
    assert not (root / "generate/cancelled.bin").exists() and not list(root.rglob(".download-*"))


@pytest.mark.parametrize("path", ["../outside.txt", "attachments/input.txt", "/absolute.txt", "C:/outside.txt"])
def test_destination_boundary(files, path):
    run, root = files
    assert run("/small.txt", path=path).startswith("错误：")
    assert not list(root.rglob(".download-*"))


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/a", "http://user:pass@example.com/file",
                                  "http://127.0.0.1/a", "http://[::1]/a", "http://169.254.169.254/a", "http://224.0.0.1/a"])
def test_unsupported_urls_and_private_addresses_are_rejected(tmp_path, url):
    result = download.download_url(url, root=tmp_path)
    assert result.startswith("错误：") and not list(tmp_path.iterdir())


def test_dns_rebinding_is_prevented_and_https_keeps_original_host(monkeypatch):
    monkeypatch.setattr(download, "_addresses", lambda host, port, internal_hosts=(): ["93.184.216.34"])
    calls = []
    class Connection:
        def __init__(self, host, port, **kwargs):
            calls.append(("host", host, port))
        def request(self, method, target, headers):
            self._create_connection(("should-not-resolve.invalid", 443))
            calls.append(("request", method, target))
        def getresponse(self):
            return object()
        def close(self):
            pass
    monkeypatch.setattr(download.http.client, "HTTPSConnection", Connection)
    monkeypatch.setattr(download.socket, "create_connection", lambda address, *args: calls.append(("socket", address)))
    download._open("https://downloads.example.test/f.txt")
    assert calls[0] == ("host", "downloads.example.test", 443)
    assert ("socket", ("93.184.216.34", 443)) in calls


@pytest.fixture
def secure_files(tmp_path, monkeypatch):
    """An actual TLS server signed by a temporary private CA, not a mocked handshake."""
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "UmEkO isolated test CA")])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
          .not_valid_after(now + timedelta(days=2))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "files.example.test")]))
            .issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("files.example.test")]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    ca_file, cert_file, key_file = (tmp_path / value for value in ("ca.pem", "server.pem", "server-key.pem"))
    ca_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_file.write_bytes(leaf.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/redirect-other":
                self.send_response(302)
                self.send_header("Location", f"https://other.example.test:{self.server.server_port}/file.txt")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", "7")
            self.end_headers()
            self.wfile.write(b"fixture")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original = download._addresses
    monkeypatch.setattr(download, "_addresses", lambda host, port, internal_hosts=():
                        ["127.0.0.1"] if host in {"files.example.test", "other.example.test"}
                        else original(host, port, internal_hosts))
    root = tmp_path / "session"
    root.mkdir()

    def run(route="/file.txt", host="files.example.test", **kwargs):
        return download.download_url(f"https://{host}:{server.server_port}{route}", root=root, **kwargs)

    yield run, root, str(ca_file)
    server.shutdown(); server.server_close(); thread.join(2)


def test_private_ca_fails_with_actionable_error_then_succeeds_with_ca(secure_files):
    run, root, ca = secure_files
    failed = run("/file.txt?token=do-not-expose")
    assert failed.startswith("错误：") and "TLS_CERTIFICATE_VERIFY_FAILED" in failed
    assert "UMEKO_DOWNLOAD_CA_FILE" in failed and "UMEKO_DOWNLOAD_TLS_INSECURE_HOSTS" in failed
    assert "do-not-expose" not in failed and str(root.parent) not in failed
    assert not list(root.iterdir())
    result = json.loads(run(config=DownloadConfig(ca_file=ca)))
    assert result["ok"] and "warnings" not in result
    assert (root / result["path"]).read_bytes() == b"fixture"


def test_custom_ca_still_rejects_wrong_hostname(secure_files):
    run, root, ca = secure_files
    result = run(host="other.example.test", config=DownloadConfig(ca_file=ca))
    assert "TLS_CERTIFICATE_VERIFY_FAILED" in result
    assert not list(root.iterdir())


def test_tls_bypass_is_explicit_host_only_and_does_not_follow_redirects(secure_files):
    run, root, _ = secure_files
    config = DownloadConfig(insecure_tls_hosts=("files.example.test",))
    assert "TLS_CERTIFICATE_VERIFY_FAILED" in run(host="other.example.test", config=config)
    assert "TLS_CERTIFICATE_VERIFY_FAILED" in run("/redirect-other", config=config)
    assert not list(root.iterdir())
    result = json.loads(run(config=config))
    assert result["ok"] and "files.example.test" in result["warnings"][0]
    assert (root / result["path"]).read_bytes() == b"fixture"


@pytest.mark.parametrize("ip,allowed", [("10.1.2.3", True), ("172.16.3.4", True), ("192.168.1.2", True),
    ("fd00::1", True), ("127.0.0.1", False), ("::1", False), ("169.254.169.254", False),
    ("100.100.100.200", False), ("224.0.0.1", False), ("0.0.0.0", False), ("fe80::1", False)])
def test_internal_host_grants_do_not_allow_local_or_metadata_addresses(monkeypatch, ip, allowed):
    monkeypatch.setattr(download.socket, "getaddrinfo", lambda *args, **kwargs:
                        [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 443))])
    if allowed:
        assert download._addresses("files.internal", 443, ("files.internal",)) == [ip]
    else:
        with pytest.raises(ValueError, match="网络策略拒绝"):
            download._addresses("files.internal", 443, ("files.internal",))
    with pytest.raises(ValueError):
        download._addresses("other.internal", 443, ("files.internal",))


def test_insecure_tls_grant_does_not_grant_internal_network_access(tmp_path):
    result = download.download_url("https://127.0.0.1/file.txt", root=tmp_path,
                                   config=DownloadConfig(insecure_tls_hosts=("127.0.0.1",)))
    assert "网络策略拒绝" in result and not list(tmp_path.iterdir())


def test_one_blocked_dns_answer_rejects_entire_destination(monkeypatch):
    monkeypatch.setattr(download.socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 443)) for ip in ("10.1.2.3", "127.0.0.1")])
    with pytest.raises(ValueError, match="网络策略拒绝"):
        download._addresses("files.internal", 443, ("files.internal",))


@pytest.mark.parametrize("failure,code", [(ssl.SSLError("handshake failed"), "TLS_ERROR"),
    (socket.gaierror("host not found"), "DNS_ERROR"), (TimeoutError(), "DOWNLOAD_TIMEOUT")])
def test_connection_errors_return_visible_category_without_leaking_url(tmp_path, monkeypatch, failure, code):
    def fail(*args):
        raise failure
    monkeypatch.setattr(download, "_open", fail)
    result = download.download_url("https://files.example.test/file?token=do-not-expose", root=tmp_path)
    assert result.startswith("错误：") and code in result and "do-not-expose" not in result
    assert not list(tmp_path.iterdir())
