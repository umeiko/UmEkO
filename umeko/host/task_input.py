"""Cheap, bounded validation before machine input reaches task storage or a model."""
from __future__ import annotations

import base64
import binascii
import re


MAX_PROMPT_CHARS = 200_000
MAX_MESSAGE_PARTS = 64
_ENCODED_BLOCK_CHARS = 4096
_TOKENS = re.compile(r"[A-Za-z0-9+/_-]{32,}={0,2}")
_DATA_URL = re.compile(r"data:[^\s,\"'<>]{0,160};base64,\s*[A-Za-z0-9+/_-]{32,}", re.IGNORECASE)
_FILE_FIELD = re.compile(r'"(?:content_base64|raw)"\s*:\s*"[A-Za-z0-9+/_-]{16,}={0,2}"')
_HTTP_URL = re.compile(r"https?://[^\s<>\"'\\]+", re.IGNORECASE)
_FILE_HEADERS = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"BM", b"II*\x00",
                 b"MM\x00*", b"%PDF-", b"PK\x03\x04", b"7z\xbc\xaf\x27\x1c", b"\x1f\x8b")


class TaskInputError(ValueError):
    """Safe to return to callers: never includes supplied content or local paths."""
    def __init__(self, code: str, message: str, field: str = "prompt"):
        self.code, self.message, self.field = code, message, field
        super().__init__(f"[{code}] {message}")

    def detail(self) -> dict:
        return {"code": self.code, "message": self.message, "field": self.field,
                "retryable": False, "task_created": False,
                "next_action": "fix_request_or_ask_user",
                "hint": "不要原样重试、拆段重试或把文件改塞进其他文本字段。修正附件结构后再提交；不能正确上传时，向用户说明需要补充附件。",
                "file_transport": {
                    "mcp_rest": "prompt 写需求，可含普通 HTTP/HTTPS 下载链接；文件字节放 files: [{name: 'input.png', content_base64: '<base64 bytes>'}]。",
                    "a2a": "A2A 1.0 message.parts 中，需求用 {text: '需求'}，HTTP/HTTPS 链接可写在 text 或 {url: 'https://files.example.invalid/input.png'} 中；url 转为需求文本交给 Agent。文件字节用 {raw: '<base64 bytes>', filename: 'input.png', mediaType: 'image/png'}，SDK 的 raw 使用 bytes。",
                }}


def _file_prefix(encoded: str) -> bool:
    # Decode a small prefix only. Large/whitespace-wrapped data need no full decode.
    prefix = encoded[:128]
    try:
        data = base64.b64decode(prefix + "=" * (-len(prefix) % 4), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        return False
    return data.startswith(_FILE_HEADERS) or (data.startswith(b"RIFF") and data[8:12] == b"WEBP")


def validate_prompt(prompt: str, *, field: str = "prompt") -> None:
    if not isinstance(prompt, str) or not prompt.strip():
        raise TaskInputError("INVALID_PROMPT", "需求须为非空文本。", field)
    if len(prompt) > MAX_PROMPT_CHARS:
        raise TaskInputError("PROMPT_TOO_LARGE", "需求文本最多 200000 字符；文件内容请通过附件上传。", field)
    # Links may legitimately have long opaque paths or signed query values.
    # Leave their retrieval/usability to the Agent and its download tool.
    text = _HTTP_URL.sub("[URL]", prompt).replace("\\r", "\r").replace("\\n", "\n")
    if _DATA_URL.search(text) or _FILE_FIELD.search(text):
        raise TaskInputError("FILE_CONTENT_IN_TEXT", "文本中包含 base64 data URL 或附件 JSON，请使用附件字段传文件。", field)
    # Count runs separated only by whitespace (or escaped JSON newlines). This
    # catches wrapped encodings without a nested/repeating regex or large decode.
    end, length = 0, 0
    for match in _TOKENS.finditer(text):
        gap = text[end:match.start()]
        contiguous = not gap.strip()
        length = length + len(match[0]) if contiguous else len(match[0])
        end = match.end()
        if length >= _ENCODED_BLOCK_CHARS or (len(match[0]) >= 64 and _file_prefix(match[0])):
            raise TaskInputError("FILE_CONTENT_IN_TEXT", "文本中包含文件编码或过长的 base64 数据块，请使用附件字段传文件。", field)
