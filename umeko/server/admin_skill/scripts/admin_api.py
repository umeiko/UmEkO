#!/usr/bin/env python3
"""Cookie-authenticated UMEKO admin client; no dependencies or mutation retries."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import http.cookiejar
import json
import os
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request


SECRET_FIELDS = {"password", "api_key", "token", "access_token", "refresh_token", "client_secret", "authorization", "cookie", "input"}


def redact(value):
    if isinstance(value, dict):
        return {key: "********" if key.lower() in SECRET_FIELDS and isinstance(item, str)
                else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class AdminAPIError(RuntimeError):
    def __init__(self, status, detail):
        self.status, self.detail = status, redact(detail)
        super().__init__(json.dumps({"status": status, "error": self.detail}, ensure_ascii=True))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AdminAPIError(code, "管理入口发生重定向；请核对完整管理基址和路径前缀。")


class AdminClient:
    def __init__(self, base_url, username, password, *, ca_file=None, proxy=None, timeout=30):
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("UMEKO_ADMIN_URL 须为含可选管理前缀的 HTTP/HTTPS 基址，不含凭据、查询或片段。")
        self.base = base_url.rstrip("/")
        self.username, self.password, self.timeout = username, password, timeout
        self.cookies = http.cookiejar.CookieJar()
        context = ssl.create_default_context()
        if ca_file:
            context.load_verify_locations(cafile=ca_file)
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {}),
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(self.cookies), NoRedirect())

    def request(self, method, path, body=None):
        parsed = urllib.parse.urlsplit(path)
        decoded = urllib.parse.unquote(parsed.path)
        if (parsed.scheme or parsed.netloc or parsed.fragment or not decoded.startswith("/admin/")
                or "\\" in decoded or any(part in {".", ".."} for part in decoded.split("/"))):
            raise ValueError("仅接受 /admin/... 内部路径；管理前缀由 UMEKO_ADMIN_URL 提供。")
        payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=payload, method=method.upper(),
                                         headers={"Accept": "application/json", "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read())
            except (ValueError, UnicodeDecodeError):
                detail = "管理服务返回非 JSON 错误；请核对端口、前缀及代理规则。"
            raise AdminAPIError(exc.code, detail) from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AdminAPIError(None, "连接、超时或证书错误；先核对连接，再查询目标状态，勿盲目重试变更。") from exc

    def __enter__(self):
        self.request("POST", "/admin/login", {"username": self.username, "password": self.password})
        try:
            self.request("GET", "/admin/v1/me")
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self, *args):
        try:
            self.request("POST", "/admin/logout")
        except AdminAPIError:
            pass
        finally:
            self.cookies.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("method", choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    parser.add_argument("path", help="/admin/v1/...，不重复加部署前缀")
    parser.add_argument("--json-file", type=Path, help="UTF-8 请求 JSON 文件，避免把密钥放进命令行")
    parser.add_argument("--output", type=Path, help="保存遮蔽凭据后的 JSON")
    parser.add_argument("--secrets-output", type=Path, help="将完整响应保留到调用者指定的新文件；不得粘贴到聊天")
    args = parser.parse_args()
    try:
        values = [os.environ[name] for name in ("UMEKO_ADMIN_URL", "UMEKO_ADMIN_USERNAME", "UMEKO_ADMIN_PASSWORD")]
        body = json.loads(args.json_file.read_text(encoding="utf-8-sig")) if args.json_file else None
        with ExitStack() as stack:
            # Validate destinations before creating or rotating a one-time secret.
            private = None
            if args.secrets_output:
                descriptor = os.open(args.secrets_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                private = stack.enter_context(os.fdopen(descriptor, "w", encoding="utf-8"))
            output = stack.enter_context(args.output.open("w", encoding="utf-8")) if args.output else None
            with AdminClient(*values, ca_file=os.getenv("UMEKO_ADMIN_CA_FILE"), proxy=os.getenv("UMEKO_ADMIN_PROXY")) as client:
                result = client.request(args.method, args.path, body)
            if private:
                json.dump(result, private, ensure_ascii=False, indent=2)
            text = json.dumps(redact(result), ensure_ascii=True, indent=2) + "\n"
            if output:
                output.write(text)
            else:
                print(text, end="")
    except KeyError as exc:
        print(json.dumps({"error": "缺少本地环境变量 " + str(exc.args[0])}, ensure_ascii=True), file=sys.stderr)
        return 2
    except AdminAPIError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print(json.dumps({"error": "本地路径、URL 或 JSON 无效；请检查配置文件，不把凭据放入命令行。"}, ensure_ascii=True), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
