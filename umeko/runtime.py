"""运行时环境感知：PyInstaller 冻结检测与系统浏览器嗅探。

冻结（离线包）时资源相对 exe 所在目录（app_dir）；非冻结为项目根。
领域特定的外部工具解析（node/mmdc 等）不属于基座，由各领域项目自行实现。
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_dir() -> Path:
    """应用根目录：冻结时为 exe 所在目录，否则为项目根。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


# Windows 常见 Chrome / Edge 安装路径（Program Files 环境变量展开）
_WIN_BROWSER_CANDIDATES = (
    r"{PF}\Google\Chrome\Application\chrome.exe",
    r"{PF86}\Google\Chrome\Application\chrome.exe",
    r"{LOCAL}\Google\Chrome\Application\chrome.exe",
    r"{PF}\Microsoft\Edge\Application\msedge.exe",
    r"{PF86}\Microsoft\Edge\Application\msedge.exe",
)

_MAC_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def sniff_browser() -> str | None:
    """嗅探系统浏览器（Chrome/Edge）安装路径，与是否冻结无关。

    Windows 查常见安装目录，macOS 查 /Applications，最后兜底 PATH。
    """
    if sys.platform == "win32":
        mapping = {
            "PF": os.getenv("ProgramFiles", r"C:\Program Files"),
            "PF86": os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            "LOCAL": os.getenv("LOCALAPPDATA", ""),
        }
        for tpl in _WIN_BROWSER_CANDIDATES:
            p = Path(tpl.format(**mapping))
            if p.is_file():
                return str(p)
    elif sys.platform == "darwin" and _MAC_CHROME.is_file():
        return str(_MAC_CHROME)
    for name in ("chrome", "google-chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    return None
