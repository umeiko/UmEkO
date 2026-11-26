"""Bounded HTTP(S) fetches with pinned DNS and administrator-scoped trust."""
from __future__ import annotations

from email.message import Message
from html.parser import HTMLParser
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
from ..config import DownloadConfig, normalize_download_host
from ..file_operations import bounded_path
from ..skill_security import guard_skill_write

MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_FETCH_BYTES = 1024 * 1024
MAX_FETCH_CHARS = 12_000
MAX_REDIRECTS = 5
FETCH_MODES = ("auto", "text", "download")
_HTML_TYPES = {"text/html", "application/xhtml+xml"}
_INTERNAL_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "fc00::/7",
))
_METADATA_IPS = frozenset(ipaddress.ip_address(value) for value in (
    "100.100.100.200", "fd00:ec2::254", "fd20:ce::254",
))


def _network_key(host: str) -> str:
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return host
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return str(ip.ipv4_mapped)
    return str(ip)


def _addresses(host: str, port: int, blocked_hosts: tuple[str, ...] = ()) -> list[str]:
    blocked = {_network_key(name) for name in blocked_hosts}
    if _network_key(host) in blocked:
        raise ValueError("下载地址被网络策略拒绝：主机命中 UMEKO_DOWNLOAD_BLOCKED_HOSTS 黑名单")
    addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    for address in addresses:
        key = _network_key(address)
        if key in blocked:
            raise ValueError("下载地址被网络策略拒绝：解析到的 IP 命中 UMEKO_DOWNLOAD_BLOCKED_HOSTS 黑名单")
        ip = ipaddress.ip_address(key)
        public = ip.is_global and not ip.is_multicast and not ip.is_reserved
        internal = any(ip in network for network in _INTERNAL_NETWORKS)
        if ip in _METADATA_IPS or not (public or internal):
            raise ValueError("下载地址被网络策略拒绝：不允许回环、链路本地、保留地址或云元数据地址")
    if not addresses:
        raise ValueError("文件主机没有可用的 DNS 地址")
    return addresses


def _open(url: str, config: DownloadConfig = DownloadConfig()):
    if not isinstance(url, str) or not url or any(char.isspace() for char in url):
        raise ValueError("请提供有效的 HTTP/HTTPS 文件网址")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("仅支持不含账号密码的 HTTP/HTTPS 文件网址")
    host = normalize_download_host(parsed.hostname)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = _addresses(host, port, config.blocked_hosts)
    if parsed.scheme == "https":
        context = ssl.create_default_context()
        if host in config.insecure_tls_hosts:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        elif config.ca_file:
            # Append the enterprise CA; keep public roots and hostname verification.
            context.load_verify_locations(cafile=config.ca_file)
        connection = http.client.HTTPSConnection(host, port, timeout=10, context=context)
    else:
        connection = http.client.HTTPConnection(host, port, timeout=10)

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


class _PageText(HTMLParser):
    _hidden = {"script", "style", "template", "noscript", "svg", "nav", "footer"}
    _void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    _blocks = {"article", "blockquote", "br", "dd", "div", "dl", "dt", "h1", "h2", "h3", "h4", "h5",
               "h6", "hr", "li", "main", "p", "pre", "section", "td", "th", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.title = []
        self.in_head = self.in_title = False
        self.hidden_tag = None
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if self.hidden_tag:
            if tag == self.hidden_tag:
                self.hidden_depth += 1
            return
        attributes = dict(attrs)
        if tag in self._hidden or (tag not in self._void and (
            "hidden" in attributes or attributes.get("aria-hidden") == "true"
        )):
            self.hidden_tag, self.hidden_depth = tag, 1
        elif tag == "head":
            self.in_head = True
        elif tag == "body":
            self.in_head = self.in_title = False
        elif tag == "title":
            self.in_title = True
        elif tag in self._blocks:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.hidden_tag:
            if tag == self.hidden_tag:
                self.hidden_depth -= 1
                if self.hidden_depth == 0:
                    self.hidden_tag = None
            return
        if tag == "head" or tag == "body":
            self.in_head = self.in_title = False
        elif tag == "title":
            self.in_title = False
        elif tag in self._blocks:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.hidden_tag:
            return
        if self.in_title:
            self.title.append(data)
        elif not self.in_head:
            self.parts.append(re.sub(r"\s+", " ", data))


def _chunks(response, started, should_cancel, limit=None):
    while limit is None or limit > 0:
        raise_if_cancelled(should_cancel)
        if time.monotonic() - started > 120:
            raise ValueError("读取网址超时（120 秒）")
        chunk = response.read1(64 * 1024 if limit is None else min(limit, 64 * 1024))
        if not chunk:
            return
        yield chunk
        if limit is not None:
            limit -= len(chunk)


def _read_text(response, media_type, length, started, should_cancel):
    raw = b"".join(_chunks(response, started, should_cancel, MAX_FETCH_BYTES + 1))
    raise_if_cancelled(should_cancel)
    truncated = len(raw) > MAX_FETCH_BYTES
    if not truncated and length is not None and len(raw) != length:
        raise ValueError("网页读取中断，实际大小与声明大小不一致")
    data = raw[:MAX_FETCH_BYTES]
    charset = response.headers.get_content_charset()
    if media_type in _HTML_TYPES and not charset:
        meta = re.search(rb"""<meta\b[^>]{0,512}\bcharset\s*=\s*["']?([\w-]+)""", data[:4096], re.I)
        if meta:
            charset = meta.group(1).decode("ascii")
    if data.startswith(b"\xef\xbb\xbf"):
        charset = "utf-8-sig"
    elif data.startswith((b"\xff\xfe", b"\xfe\xff")):
        charset = "utf-16"
    try:
        content = data.decode(charset or "utf-8", errors="replace")
    except LookupError:
        content = data.decode("utf-8", errors="replace")
    title = ""
    if media_type in _HTML_TYPES:
        page = _PageText()
        try:
            page.feed(content)
            page.close()
        except AssertionError as exc:
            raise ValueError("网页 HTML 格式异常，请用 download 模式保存原始响应") from exc
        title = " ".join("".join(page.title).split())[:300]
        lines = (line.strip() for line in "".join(page.parts).splitlines())
        content = "\n".join(filter(None, lines))
    return {"ok": True, "result": "已读取网址正文" if content.strip() else "已访问网址，响应中没有可读取的正文",
            "kind": "webpage" if media_type in _HTML_TYPES else "text", "http_status": 200,
            "content_type": media_type, "title": title, "content": content[:MAX_FETCH_CHARS],
            "truncated": truncated or len(content) > MAX_FETCH_CHARS, "files": []}


def _result_json(result, insecure_hosts_used):
    if insecure_hosts_used:
        result["warnings"] = ["管理员已为以下主机关闭 TLS 证书校验：" + ", ".join(sorted(insecure_hosts_used))]
    return json.dumps(result, ensure_ascii=False)


def fetch_url(url: str, path: str = "", overwrite: bool = False, *, root: Path,
                 allowed_roots: tuple[Path, ...] | None = None, default_dir: str = "downloads",
                 should_cancel: CancelCheck = None, config: DownloadConfig = DownloadConfig(), mode: str = "auto") -> str:
    """Read a bounded text preview or publish a complete file atomically."""
    temporary, connection = None, None
    started = time.monotonic()
    insecure_hosts_used = set()
    try:
        if not isinstance(path, str) or not isinstance(overwrite, bool):
            raise ValueError("path 须为字符串，overwrite 须为布尔值")
        if mode not in FETCH_MODES or (mode == "text" and (path or overwrite)):
            raise ValueError("mode 须为 auto、text 或 download；text 不接受 path 或 overwrite")
        if path and (Path(path).is_absolute() or PureWindowsPath(path).drive):
            raise ValueError("下载目标必须使用当前工作区内的相对路径")
        target = bounded_path(root, path, allowed_roots) if path else None
        if target is not None:
            guard_skill_write(target)
        if target is not None and target.exists() and (not overwrite or not target.is_file()):
            raise ValueError("目标已存在，请换一个文件名；只有文件支持 overwrite=true")
        for step in range(MAX_REDIRECTS + 1):
            raise_if_cancelled(should_cancel)
            connection, response = _open(url, config)
            parsed = urlsplit(url)
            host = normalize_download_host(parsed.hostname)
            if parsed.scheme == "https" and host in config.insecure_tls_hosts:
                insecure_hosts_used.add(host)
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
        media_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        read_text = mode == "text" or (mode == "auto" and not path and not overwrite
                                      and media_type in _HTML_TYPES
                                      and response.headers.get_content_disposition() != "attachment")
        length_header = response.getheader("Content-Length")
        if length_header is not None and not length_header.isdecimal():
            raise ValueError("下载文件超过 20 MB 或大小声明无效")
        length = int(length_header) if length_header is not None else None
        if not read_text and length is not None and length > MAX_DOWNLOAD_BYTES:
            raise ValueError("下载文件超过 20 MB 或大小声明无效")
        if response.getheader("Content-Encoding", "identity").lower() not in {"", "identity"}:
            raise ValueError("服务器返回了不支持的内容编码，请使用提供原始响应的链接")
        if read_text:
            if media_type not in _HTML_TYPES and not media_type.startswith("text/") and media_type != "application/json":
                raise ValueError("响应未声明为网页或文本，请用 download 模式保存原文件")
            result = _read_text(response, media_type, length, started, should_cancel)
            return _result_json(result, insecure_hosts_used)
        if target is None:
            target = bounded_path(root, f"{default_dir}/{_filename(url, response.headers)}", allowed_roots)
        guard_skill_write(target)
        if target.exists() and (not overwrite or not target.is_file()):
            raise ValueError("目标已存在，请换一个文件名；只有文件支持 overwrite=true")
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".download-", delete=False) as output:
            temporary = Path(output.name)
            for chunk in _chunks(response, started, should_cancel):
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError("下载文件超过 20 MB，已停止并清除未完成文件")
                output.write(chunk)
        if length is not None and size != length:
            raise ValueError("文件下载中断，实际大小与声明大小不一致")
        raise_if_cancelled(should_cancel)
        # Recheck containment after transfer; never overwrite existing files implicitly.
        bounded_path(root, target, allowed_roots)
        guard_skill_write(target)
        if overwrite:
            temporary.replace(target)
        else:
            os.link(temporary, target)
        relative = target.relative_to(root.resolve()).as_posix()
        result = {"ok": True, "result": "文件下载完成", "path": relative, "size": size, "files": [relative]}
        return _result_json(result, insecure_hosts_used)
    except ssl.SSLCertVerificationError as exc:
        host = urlsplit(url).hostname or "文件主机"
        return (f"错误：文件下载失败 [TLS_CERTIFICATE_VERIFY_FAILED]：{host} 的 HTTPS 证书校验失败"
                f"（{exc.verify_message}）。请管理员配置 UMEKO_DOWNLOAD_CA_FILE 为公司 CA 的 PEM 文件后重启。"
                "证书过期或域名不匹配时需修复文件服务证书。"
                "MODEL_CA_FILE 只用于模型接口。若暂时无法提供 CA，可由管理员将该精确主机名加入 "
                "UMEKO_DOWNLOAD_TLS_INSECURE_HOSTS 后重启；工具不会自动跳过证书校验。")
    except ssl.SSLError as exc:
        return ("错误：文件下载失败 [TLS_ERROR]：TLS 握手失败"
                f"（{getattr(exc, 'reason', None) or type(exc).__name__}），请检查目标 HTTPS 服务")
    except socket.gaierror:
        return "错误：文件下载失败 [DNS_ERROR]：无法解析文件主机，请检查网址和服务器的内网 DNS 配置"
    except TimeoutError:
        return "错误：文件下载失败 [DOWNLOAD_TIMEOUT]：连接或读取超时，请检查服务器到文件主机的网络连通性"
    except (OSError, ValueError, UnicodeError, http.client.HTTPException) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else (getattr(exc, "strerror", None) or type(exc).__name__)
        return f"错误：文件下载失败：{reason}"
    finally:
        if connection is not None:
            connection.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


# Python callers from earlier integrations share the same implementation.
download_url = fetch_url
