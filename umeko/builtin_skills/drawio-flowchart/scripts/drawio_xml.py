"""低层 draw.io 文件处理与导出，独立于各技能的布局。"""

from __future__ import annotations

import http.client
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import struct
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zlib

logger = logging.getLogger(__name__)
_EXPORT_SECONDS = 45
_MAX_SERVERS = 8
_MAX_XML_BYTES = 4 * 1024 * 1024
_MAX_IMAGE_BYTES = 16 * 1024 * 1024
_IMAGE_TYPES = {"png": "image/png", "svg": "image/svg+xml"}
_SVG = "http://www.w3.org/2000/svg"
_XHTML = "http://www.w3.org/1999/xhtml"
_XLINK = "http://www.w3.org/1999/xlink"


def extract_xml(text: str) -> str:
    """从 LLM 输出提取 XML：优先 ```xml 代码块，否则取第一个 <mxfile> 起到结尾。"""
    m = re.search(r"```(?:xml)?\s*\n(.*?)```", text, re.S)
    candidate = m.group(1) if m else text
    start = candidate.find("<mxfile")
    if start == -1:
        return ""
    end = candidate.rfind("</mxfile>")
    if end == -1:
        return ""
    return candidate[start : end + len("</mxfile>")]


def sanitize_xml(text: str) -> str:
    """修复模型的常见违规：value 属性里原样写了 <br/>（非法 XML），自动转义。"""
    def _fix(m: re.Match) -> str:
        fixed = re.sub(r"<br\s*/?>", "&lt;br/&gt;", m.group(1))
        if fixed != m.group(1):
            logger.warning("自动转义 value 属性中的字面 <br/>")
        return f'value="{fixed}"'
    return re.sub(r'value="([^"]*)"', _fix, text)


def apply_font(xml_text: str, family: str | None, size: str | None) -> str:
    """给所有 cell 的 style 注入/覆盖 fontFamily 与 fontSize。

    确定性后处理（不信任 LLM 照抄骨架里的字体字段）：family/size 为
    None 的项不注入。字号按原样写入（drawio 接受小数如 10.5），
    无法解析为数字时打 warning 并跳过字号注入。
    注意：字体需本机已安装，未安装时 draw.io 静默回退默认字体。
    """
    props: dict[str, str] = {}
    if family:
        props["fontFamily"] = family
    if size:
        try:
            float(size)
        except ValueError:
            logger.warning("DRAWIO_FONT_SIZE=%r 不是数字，跳过字号注入", size)
        else:
            props["fontSize"] = size
    if not props:
        return xml_text

    root = ET.fromstring(xml_text)
    for cell in root.iter("mxCell"):
        style = cell.get("style")
        if not style:
            continue
        parts = [p for p in style.split(";") if p]
        keys = [p.split("=", 1)[0] for p in parts]
        for k, v in props.items():
            if k in keys:
                parts[keys.index(k)] = f"{k}={v}"
            else:
                parts.append(f"{k}={v}")
        cell.set("style", ";".join(parts) + ";")
    logger.info("[drawio] 字体注入：%s", " ".join(f"{k}={v}" for k, v in props.items()))
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _configured_renderer(config):
    return config.get("drawio_path") or os.getenv("UMEKO_DRAWIO_PATH") or os.getenv("DRAWIO_PATH")


def _renderer(config):
    configured = _configured_renderer(config)
    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute() or not candidate.is_file():
            return None, "管理员配置的 draw.io 可执行文件不存在或不是绝对路径"
        return str(candidate), None
    found = shutil.which("draw.io") or shutil.which("drawio")
    return found, None if found else "未配置 draw.io 桌面版，已保存可直接打开编辑的 .drawio"


def _export_detail(value, renderer, source, workdir, session_root):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    detail = str(value or "").strip()
    for absolute, label in ((str(source), "<图文件>"), (str(workdir), "<产物目录>"),
                            (str(session_root), "<会话目录>"), (renderer or "", "<draw.io>")):
        if absolute:
            detail = detail.replace(absolute, label).replace(absolute.replace("\\", "/"), label)
    return detail[-1000:]


def _render_targets(config):
    urls = config.get("render_urls", [])
    if not isinstance(urls, list) or len(urls) > _MAX_SERVERS:
        raise ValueError(f"render_urls 须为最多 {_MAX_SERVERS} 个 HTTPS 地址组成的列表")
    targets, problems, seen = [], [], set()
    for number, value in enumerate(urls, 1):
        try:
            if not isinstance(value, str) or any(not 33 <= ord(c) <= 126 for c in value) or "\\" in value:
                raise ValueError()
            url = urlsplit(value)
            if (url.scheme != "https" or not url.hostname or not url.path or url.path == "/"
                    or url.username is not None or url.password is not None or "?" in value or "#" in value):
                raise ValueError()
            if url.port == 0:
                raise ValueError()
            key = (url.hostname, url.port or 443, url.path)
        except ValueError:
            problems.append(f"网络渲染服务 #{number} 须填写完整 HTTPS 接口地址，且不能包含凭据、查询参数或片段")
            continue
        if key not in seen:
            seen.add(key)
            targets.append((number, key))
    return targets, problems


def _check_svg(data):
    # SVG may be opened directly using the service origin. Keep native draw.io
    # labels (including XHTML in foreignObject), but reject active resources.
    svg = data.decode("utf-8-sig")
    declaration = re.match(r"^<\?xml\s[^?]*\?>", svg)
    if declaration:
        encoding = re.search(r"encoding\s*=\s*(['\"])([^'\"]+)\1", declaration[0], re.I)
        if encoding and encoding[2].lower() != "utf-8":
            raise ValueError("SVG 必须使用 UTF-8 编码")
    svg = re.sub(r"^<\?xml\s[^?]*\?>", "", svg, count=1)
    if "<?" in svg or re.search(r"<!\s*(?:DOCTYPE|ENTITY)", svg, re.I):
        raise ValueError("SVG 含外部处理指令或实体声明")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise ValueError("SVG 内容不是有效 XML") from exc
    if root.tag != f"{{{_SVG}}}svg":
        raise ValueError("响应不是 SVG 图像")

    def check_style(value):
        # Remove fragment-only CSS references. Reject external or obfuscated URLs.
        css = re.sub(r"url\(\s*(['\"]?)#[\w.:-]+\1\s*\)", "", value, flags=re.I)
        if re.search(r"(?:url|(?:-webkit-)?image-set|image|src|expression)\s*\(|@(?:import|font-face)|\\|/\*", css, re.I):
            raise ValueError("SVG 含未允许的样式资源引用")

    for node in root.iter():
        namespace, _, tag = node.tag.rpartition("}")
        tag = tag.casefold()
        if namespace not in {"{" + _SVG, "{" + _XHTML} or tag in {
            "script", "iframe", "object", "embed", "link", "meta", "base", "form", "input", "button",
            "audio", "video", "source", "animate", "animatemotion", "animatetransform", "set", "discard",
        }:
            raise ValueError("SVG 含未允许的活动元素")
        if tag == "style":
            check_style("".join(node.itertext()))
        for name, value in node.attrib.items():
            attr = name.rsplit("}", 1)[-1].casefold()
            # diagram metadata is inert. URLs and event handlers are not.
            if attr.startswith("on") or attr in {"base", "srcdoc", "srcset", "action", "formaction", "poster", "ping"}:
                raise ValueError("SVG 含未允许的活动属性")
            if attr in {"src", "href"}:
                if re.fullmatch(r"#[\w.:-]+", value):
                    continue
                if (tag in {"image", "img"} and name in {"href", "src", f"{{{_XLINK}}}href"}
                        and re.fullmatch(r"data:image/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+", value, re.I)):
                    continue
                raise ValueError("SVG 含外部链接或不支持的内嵌资源")
            if attr in {"style", "fill", "stroke", "filter", "clip-path", "mask", "marker-start", "marker-mid", "marker-end", "cursor"}:
                check_style(value)


def _check_remote_image(data, fmt):
    if fmt == "svg":
        _check_svg(data)
        return
    if (len(data) < 45 or not data.startswith(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
            or not data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")):
        raise ValueError("响应不是完整 PNG 图像")
    width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if not 0 < width * height <= 64 * 1024 * 1024:
        raise ValueError("PNG 尺寸超出限制")
    view = memoryview(data)
    offset, has_pixels = 8, False
    while offset + 12 <= len(view):
        length, kind = struct.unpack_from(">I4s", view, offset)
        end = offset + 8 + length
        if end + 4 > len(view) or zlib.crc32(view[offset + 4:end]) != struct.unpack_from(">I", view, end)[0]:
            break
        if kind == b"IEND":
            if length == 0 and end + 4 == len(view) and has_pixels:
                return
            break
        has_pixels |= kind == b"IDAT" and length > 0
        offset = end + 4
    raise ValueError("PNG 数据块缺失或校验失败")


def _request_image(endpoint, payload, fmt, context, timeout):
    deadline = time.monotonic() + timeout
    result = []

    def request():
        host, port, path = endpoint
        connection = http.client.HTTPSConnection(host, port, context=context, timeout=timeout)
        try:
            connection.connect()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            connection.sock.settimeout(remaining)
            connection.request("POST", path, payload, {"Content-Type": "application/json", "Accept": _IMAGE_TYPES[fmt]})
            with connection.getresponse() as response:
                # Do not follow redirects or include the upstream error body in diagnostics.
                if response.status != 200:
                    detail = {422: "XML 或渲染参数不被接受", 503: "渲染引擎不可用"}.get(response.status)
                    raise ValueError(f"HTTP {response.status}" + (f"（{detail}）" if detail else ""))
                media = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
                if media != _IMAGE_TYPES[fmt]:
                    raise ValueError("响应 Content-Type 与所请求的图像格式不一致")
                remaining = _MAX_IMAGE_BYTES + 1
                chunks = []
                while remaining and time.monotonic() < deadline:
                    chunk = response.read1(min(65536, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if time.monotonic() >= deadline:
                    raise ValueError("请求超时")
                if not remaining:
                    raise ValueError("图像超过 16 MiB")
                data = b"".join(chunks)
                length = response.getheader("Content-Length")
                if length is not None and (not length.isdecimal() or int(length) != len(data)):
                    raise ValueError("响应未完整传输")
                _check_remote_image(data, fmt)
                result.append(data)
        except ssl.SSLCertVerificationError:
            result.append(ValueError("TLS 证书校验失败"))
        except TimeoutError:
            result.append(ValueError("请求超时"))
        except UnicodeError:
            result.append(ValueError("SVG 不是有效的 UTF-8"))
        except (OSError, http.client.HTTPException):
            result.append(ValueError("连接或响应读取失败"))
        except ValueError as exc:
            result.append(exc)
        finally:
            connection.close()

    # A socket inactivity timeout alone cannot bound DNS or a slow trickle.
    worker = threading.Thread(target=request, daemon=True)
    worker.start()
    worker.join(timeout)
    if not result or time.monotonic() >= deadline:
        raise ValueError("请求超时")
    if isinstance(result[0], Exception):
        raise result[0]
    return result[0]


def _network_export(source, fmt, scale, bg, targets, budget, attempts):
    if not targets or fmt not in _IMAGE_TYPES:
        return None
    try:
        with source.open("rb") as stream:
            xml = stream.read(_MAX_XML_BYTES + 1)
        if len(xml) > _MAX_XML_BYTES:
            raise ValueError("源文件超过 4 MiB")
        if not re.match(rb"\s*(?:<\?xml[^?]*\?>\s*)?<mxfile[\s>]", xml) or re.search(rb"<!\s*(?:DOCTYPE|ENTITY)", xml, re.I):
            raise ValueError("网络渲染要求无 DTD 或实体声明的 mxfile XML")
        params = {"xml": xml.decode("utf-8"), "format": fmt, "scale": scale if fmt == "png" else 1}
        if bg:
            params["bg"] = bg
        payload = json.dumps(params, ensure_ascii=False).encode("utf-8")
        context = ssl.create_default_context()
        ca_file = os.getenv("UMEKO_DRAWIO_RENDER_CA_FILE")
        if ca_file:
            try:
                context.load_verify_locations(cafile=ca_file)
            except (OSError, ValueError) as exc:
                raise ValueError("无法加载管理员配置的渲染服务 CA") from exc
    except (OSError, UnicodeError):
        attempts.append("网络渲染无法读取 UTF-8 源文件或加载 TLS 配置")
        return None
    except ValueError as exc:
        attempts.append(f"网络渲染：{exc}")
        return None
    deadline = time.monotonic() + budget
    for offset, (number, endpoint) in enumerate(targets):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            return _request_image(endpoint, payload, fmt, context, min(8, remaining / (len(targets) - offset)))
        except ValueError as exc:
            attempts.append(f"网络渲染服务 #{number}：{exc}")
    return None


def _local_export(renderer, source, temporary, fmt, scale, timeout):
    command = [renderer, "--export", "--format", fmt, "--output", str(temporary)]
    if fmt == "png":
        command += ["--scale", str(scale)]
    command.append(str(source))
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if process.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
        detail = " ".join((process.stdout[-400:] + " " + process.stderr[-400:]).strip().splitlines())
        raise ValueError(f"退出码 {process.returncode} 或没有有效文件" + (f"：{detail}" if detail else ""))


def export_diagram(source, session_root, formats, config, *, python_fallback=False):
    """Try approved network endpoints in order, then the configured local renderer."""
    files, exports, errors, warnings = [], [], [], []
    if not formats:
        return files, exports, errors, warnings
    workdir, name = source.parent, source.stem
    scale = 2
    try:
        if isinstance(config, Path):
            config = json.loads(config.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("config.json 必须为对象")
        scale = float(config.get("scale", 2))
        if not math.isfinite(scale) or not 0 < scale <= 8:
            raise ValueError("scale 必须大于 0 且不超过 8")
    except (OSError, UnicodeError, ValueError, TypeError):
        config = None
    targets, bg = [], None
    if config is not None and any(fmt in _IMAGE_TYPES for fmt in formats):
        try:
            bg = config.get("render_bg")
            if bg is not None and (not isinstance(bg, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", bg)):
                raise ValueError("render_bg 须为 #RRGGBB 或 null")
            targets, issues = _render_targets(config)
            warnings.extend(issues)
        except ValueError as exc:
            warnings.append(f"网络渲染配置无效：{exc}。将使用本地导出。")

    renderer, local_warning = None, "导出配置无效，请检查 assets/config.json 和 scale"
    render = None
    if config is not None:
        try:
            renderer, local_warning = _renderer(config)
        except (OSError, TypeError, ValueError):
            local_warning = "drawio_path 须为可访问的可执行文件绝对路径"
        if not renderer and python_fallback and not _configured_renderer(config):
            try:
                from umeko_drawio import render
            except ImportError:
                local_warning += "；也可在宿主安装 umeko-drawio"

    budget = _EXPORT_SECONDS / len(formats)
    for fmt in formats:
        deadline = time.monotonic() + budget
        output = workdir / f"{name}.{fmt}"
        output.resolve().relative_to(workdir)
        # An old preview cannot represent the new source, even if export fails.
        output.unlink(missing_ok=True)
        attempts = []
        code = "renderer_unavailable" if config is not None else "export_config_invalid"
        try:
            print(f"draw.io 导出 {fmt}", file=sys.stderr)
            with tempfile.TemporaryDirectory(prefix=".drawio-export-", dir=workdir) as directory:
                temporary = Path(directory) / output.name
                data = _network_export(source, fmt, scale, bg, targets, budget * 0.6, attempts) if targets else None
                if data is not None:
                    temporary.write_bytes(data)
                    backend = "network"
                elif renderer:
                    _local_export(renderer, source, temporary, fmt, scale, max(0.1, deadline - time.monotonic()))
                    backend = "local"
                elif render and fmt in _IMAGE_TYPES:
                    font_files = [path for path in os.getenv("DRAWIO_EXPORT_FONT_FILES", "").split(os.pathsep) if path]
                    image = render(source.read_text(encoding="utf-8"), fmt,
                                   scale=scale if fmt == "png" else 1, font_files=font_files,
                                   font_family=os.getenv("DRAWIO_EXPORT_FONT_FAMILY"))
                    temporary.write_bytes(image.data)
                    if image.warnings:
                        warnings.append(f"{fmt} 导出器报告 {len(image.warnings)} 项渲染警告")
                    backend = "python"
                else:
                    detail = local_warning or "该格式需要 draw.io 本地二进制"
                    if config is not None:
                        detail += "；请由管理员检查 drawio_path / UMEKO_DRAWIO_PATH / DRAWIO_PATH 和运行环境。"
                    message = f"{fmt} 未导出：" + "；".join([*attempts, detail])
                    errors.append({"format": fmt, "code": "export_failed" if attempts else code, "message": message})
                    exports.append({"format": fmt, "ok": False, "error": message})
                    continue
                temporary.replace(output)
            if attempts:
                warnings.extend(f"{fmt}：{attempt}" for attempt in attempts)
            relative = output.relative_to(session_root).as_posix()
            files.append(relative)
            exports.append({"format": fmt, "ok": True, "path": relative, "backend": backend})
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            if isinstance(exc, subprocess.TimeoutExpired):
                code = "export_timeout"
                reason = f"draw.io 导出超时（{exc.timeout:g}s）"
                captured = _export_detail(exc.stderr or exc.stdout, renderer, source, workdir, session_root)
                if captured:
                    reason += "：" + captured
            else:
                code = "export_failed"
                reason = _export_detail(exc, renderer, source, workdir, session_root)
            message = f"{fmt} 导出失败：" + "；".join([*attempts, reason])
            errors.append({"format": fmt, "code": code, "message": message})
            exports.append({"format": fmt, "ok": False, "error": message})
    return files, exports, errors, warnings
