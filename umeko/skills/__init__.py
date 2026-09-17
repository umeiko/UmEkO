"""最小 Skill 抽象：name / description / inputSchema(JSON Schema) / handler。

Schema 与 MCP 工具的 inputSchema 同构，后续要接入 MCP 时可直接映射；
OpenAI function calling 的 tools 定义也由它派生。
"""

from .base import Skill
from .file_tools import build_file_tools, resolve_readable_path

__all__ = ["Skill", "build_file_tools", "resolve_readable_path"]
