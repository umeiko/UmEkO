"""Bounded HTTP(S) downloads into the current workspace, with pinned public DNS."""
from __future__ import annotations

from email.message import Message
import http.client
import ipaddress
import json
import os
from pathlib import Path, PureWindowsPath
import re
import socket
import ssl
import tempfile
import time
from urllib.parse import quote, unquote, urljoin, urlsplit

from ..cancellation import CancelCheck, raise_if_cancelled
from ..file_operations import bounded_path

MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5


def _addresses(host: str, port: int) -> list[str]:
    addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(ip.split("%", 1)[0]).is_global
                            or ipaddress.ip_address(ip.split("%", 1)[0]).is_multicast for ip in addresses):
        raise ValueError("仅允许下载公网 HTTP/HTTPS 文件，不允许本机、内网或保留地址")
    return addresses


def _open(url: str):
    if not isinstance(url, str) or not url or any(char.isspace() for char in url):
        raise ValueError("请提供有效的 HTTP/HTTPS 文件网址")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("仅支持不含账号密码的 HTTP/HTTPS 文件网址")
    host = parsed.hostname.encode("idna").decode("ascii")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = _addresses(host, port)
    connection = (http.client.HTTPSConnection(host, port, timeout=10, context=ssl.create_default_context())
                  if parsed.scheme == "https" else http.client.HTTPConnection(host, port, timeout=10))

    def connect(address, timeout=10, source_address=None):
        # Pin the validated IPs; HTTPS still authenticates the original hostname/SNI.
        failure = None
        for ip in addresses:
            try:
                return socket.create_connection((ip, port), timeout, source_address)
            except OSError as exc:
                failure = exc
        raise failure

    connection._create_connection = connect
    target = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
    if parsed.query:
        target += "?" + quote(parsed.query, safe="/%?:@!$&'()*+,;=-._~")
    try:
        connection.request("GET", target, headers={"User-Agent": "UmEkO-file-download", "Accept-Encoding": "identity"})
        return connection, connection.getresponse()
    except BaseException:
        connection.close()
        raise


def _filename(url: str, headers) -> str:
    disposition = Message()
    disposition["content-disposition"] = headers.get("Content-Disposition", "")
    raw = disposition.get_filename() or unquote(urlsplit(url).path.rsplit("/", 1)[-1]) or "download.bin"
    # Server-suggested names must remain a single portable filename.
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", raw).strip(" .")[:160]
    if not name or name.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)]}:
        name = "download.bin"
    return name


def download_url(url: str, path: str = "", overwrite: bool = False, *, root: Path,
                 allowed_roots: tuple[Path, ...] | None = None, default_dir: str = "downloads",
                 should_cancel: CancelCheck = None) -> str:
    """Stream at most 20 MiB; publish atomically only after a complete successful transfer."""
    temporary, connection = None, None
    started = time.monotonic()
    try:
        if not isinstance(path, str) or not isinstance(overwrite, bool):
            raise ValueError("path 须为字符串，overwrite 须为布尔值")
        if path and (Path(path).is_absolute() or PureWindowsPath(path).drive):
            raise ValueError("下载目标必须使用当前工作区内的相对路径")
        target = bounded_path(root, path, allowed_roots) if path else None
        if target is not None and target.exists() and (not overwrite or not target.is_file()):
            raise ValueError("目标已存在，请换一个文件名；只有文件支持 overwrite=true")
        for step in range(MAX_REDIRECTS + 1):
            raise_if_cancelled(should_cancel)
            connection, response = _open(url)
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                connection.close()
                if not location or step == MAX_REDIRECTS:
                    raise ValueError("下载重定向无效或次数过多")
                url = urljoin(url, location)
                continue
            break
        if response.status != 200:
            raise ValueError(f"文件下载失败：HTTP {response.status}")
        length = response.getheader("Content-Length")
        if length is not None and (not length.isdecimal() or int(length) > MAX_DOWNLOAD_BYTES):
            raise ValueError("下载文件超过 20 MB 或大小声明无效")
        if response.getheader("Content-Encoding", "identity").lower() not in {"", "identity"}:
            raise ValueError("服务器未提供原始文件传输，请使用可直接下载的文件链接")
        if target is None:
            target = bounded_path(root, f"{default_dir}/{_filename(url, response.headers)}", allowed_roots)
        if target.exists() and (not overwrite or not target.is_file()):
            raise ValueError("目标已存在，请换一个文件名；只有文件支持 overwrite=true")
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".download-", delete=False) as output:
            temporary = Path(output.name)
            while True:
                raise_if_cancelled(should_cancel)
                if time.monotonic() - started > 120:
                    raise ValueError("文件下载超时（120 秒）")
                chunk = response.read1(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError("下载文件超过 20 MB，已停止并清除未完成文件")
                output.write(chunk)
        if length is not None and size != int(length):
            raise ValueError("文件下载中断，实际大小与声明大小不一致")
        raise_if_cancelled(should_cancel)
        # Recheck containment after transfer; never overwrite existing files implicitly.
        bounded_path(root, target, allowed_roots)
        if overwrite:
            temporary.replace(target)
        else:
            os.link(temporary, target)
        relative = target.relative_to(root.resolve()).as_posix()
        return json.dumps({"ok": True, "result": "文件下载完成", "path": relative,
                           "size": size, "files": [relative]}, ensure_ascii=False)
    except (OSError, ValueError, UnicodeError, http.client.HTTPException) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else (getattr(exc, "strerror", None) or type(exc).__name__)
        return f"错误：文件下载失败：{reason}"
    finally:
        if connection is not None:
            connection.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
