"""Real isolated HTTP transfers, exact size limits, cleanup and URL/path boundaries."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

import pytest

from umeko.cancellation import OperationCancelled
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
    monkeypatch.setattr(download, "_addresses", lambda host, port: ["127.0.0.1"] if host == "files.example.test" else addresses(host, port))
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
    monkeypatch.setattr(download, "_addresses", lambda host, port: ["93.184.216.34"])
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
