"""各功能的 Prompt 统一放在这里（模块内常量），业务代码不再内联长 prompt。

- ocr.py    read_image 的 OCR 提示词
"""

from .ocr import OCR_PROMPT

__all__ = ["OCR_PROMPT"]
