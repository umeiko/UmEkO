"""Bounded, content-based image validation and model-input preparation."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
import math
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_INPUT_PIXELS = 80_000_000
MAX_INPUT_EDGE = 65_536
MAX_IMAGE_EDGE = 2560
MAX_IMAGE_PIXELS = 4_000_000
MAX_IMAGE_BYTES = 4 * 1024 * 1024  # Binary bytes; base64 adds roughly one third.
MODEL_MIMES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


class ImageInputError(ValueError):
    """A file cannot safely be prepared for visual model input."""


def _format(header: bytes) -> str | None:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if header.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if header[:6] in {b"GIF87a", b"GIF89a"}:
        return "GIF"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "WEBP"
    if header[:2] == b"BM":
        return "BMP"
    if header[:4] in {b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"}:
        return "TIFF"
    return None


def detect_image_format(path: str | Path) -> str | None:
    """Sniff raster signatures without trusting a name or decoding pixels."""
    try:
        with Path(path).open("rb") as stream:
            return _format(stream.read(16))
    except OSError as exc:
        raise ImageInputError("无法读取图片文件") from exc


def _source(path: str | Path) -> bytes:
    p = Path(path)
    try:
        if not p.is_file():
            raise ImageInputError(f"图片文件不存在：{path}")
        if p.stat().st_size > MAX_INPUT_BYTES:
            raise ImageInputError("图片源文件超过 64 MiB，请先压缩文件或提供局部图片")
        with p.open("rb") as stream:
            data = stream.read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            raise ImageInputError("图片源文件超过 64 MiB，请先压缩文件或提供局部图片")
        return data
    except OSError as exc:
        raise ImageInputError("无法读取图片文件") from exc


def _dimensions(image: Image.Image) -> None:
    width, height = image.size
    if width < 1 or height < 1 or width * height > MAX_INPUT_PIXELS or max(width, height) > MAX_INPUT_EDGE:
        raise ImageInputError("图片尺寸超过安全解码上限（8000 万像素或单边 65536），请提供较小图片或局部图片")


def _verify(data: bytes) -> str:
    fmt = _format(data[:16])
    if fmt is None:
        raise ImageInputError("文件内容不是支持的图片格式；支持 PNG、JPEG、WebP、GIF、BMP、TIFF，不依赖文件后缀")
    try:
        # Limit decoders: PDF/EPS/SVG and external converters are never invoked.
        with Image.open(BytesIO(data), formats=[fmt]) as image:
            _dimensions(image)
            image.verify()
    except Image.DecompressionBombError as exc:
        raise ImageInputError("图片尺寸超过安全解码上限，请提供较小图片或局部图片") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, TypeError, OverflowError) as exc:
        if isinstance(exc, ImageInputError):
            raise
        raise ImageInputError("图片内容损坏或无法解码，请重新上传完整图片") from exc
    return fmt


def validate_image(path: str | Path) -> Path:
    """Validate format, container and resource bounds, independently of suffix."""
    _verify(_source(path))
    return Path(path)


@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    format: str
    source_size: tuple[int, int]
    size: tuple[int, int]
    source_format: str
    first_frame: bool = False
    oriented: bool = False

    @property
    def url(self) -> str:
        return f"data:{MODEL_MIMES[self.format]};base64," + base64.b64encode(self.data).decode("ascii")

    @property
    def note(self) -> str:
        notes = []
        resized = self.size[0] * self.size[1] < self.source_size[0] * self.source_size[1]
        if resized:
            notes.append(f"原图 {self.source_size[0]}×{self.source_size[1]}，模型输入已等比缩小至 {self.size[0]}×{self.size[1]}")
        if self.first_frame:
            notes.append("本次只分析第 1 帧/页，不代表已检查后续帧/页")
        if self.oriented:
            notes.append("已按图片 EXIF 信息校正方向")
        if self.source_format != self.format:
            notes.append(f"已将 {self.source_format} 转为 {self.format}")
        if resized:
            notes.append("缩放后无法辨认的细节应明确说明，不能猜测")
        return "；".join(notes)


def _encode(image: Image.Image, fmt: str, **options) -> bytes:
    output = BytesIO()
    image.save(output, format=fmt, **options)
    return output.getvalue()


def prepare_image(path: str | Path) -> PreparedImage:
    """Prepare only in memory; never rename, rewrite or delete the attachment."""
    data = _source(path)
    fmt = _verify(data)
    try:
        with Image.open(BytesIO(data), formats=[fmt]) as source:
            _dimensions(source)
            original = source.size
            orientation = source.getexif().get(274, 1)
            oriented = orientation in {2, 3, 4, 5, 6, 7, 8}
            # Do not enumerate all frames/pages of user-controlled GIF/TIFF.
            first_frame = fmt in {"GIF", "TIFF"} or bool(getattr(source, "is_animated", False))
            ratio = min(1.0, MAX_IMAGE_EDGE / max(original), math.sqrt(MAX_IMAGE_PIXELS / (original[0] * original[1])))
            target = (max(1, int(original[0] * ratio)), max(1, int(original[1] * ratio)))
            if ratio == 1 and fmt in MODEL_MIMES and not first_frame and not oriented and len(data) <= MAX_IMAGE_BYTES:
                source.load()  # verify() alone does not decode JPEG pixel data.
                return PreparedImage(data, fmt, original, source.size, fmt)
            # thumbnail uses the JPEG decoder's reduced-resolution path where
            # available; bounds are applied before EXIF transpose/copy/convert.
            source.thumbnail(target, Image.Resampling.LANCZOS, reducing_gap=3.0)
            source.load()
            ImageOps.exif_transpose(source, in_place=True)
            alpha = "A" in source.getbands() or "transparency" in source.info
            image = source.convert("RGBA" if alpha else "RGB")
            try:
                for _ in range(12):
                    output_format = "JPEG" if fmt == "JPEG" and not alpha else "PNG"
                    output = _encode(image, output_format, **({"quality": 90} if output_format == "JPEG" else {}))
                    if len(output) <= MAX_IMAGE_BYTES:
                        return PreparedImage(output, output_format, original, image.size, fmt, first_frame, oriented)
                    if not alpha:
                        for quality in (85, 75):
                            output = _encode(image, "JPEG", quality=quality)
                            if len(output) <= MAX_IMAGE_BYTES:
                                return PreparedImage(output, "JPEG", original, image.size, fmt, first_frame, oriented)
                    smaller = (max(1, int(image.width * .75)), max(1, int(image.height * .75)))
                    if smaller == image.size:
                        break
                    resized = image.resize(smaller, Image.Resampling.LANCZOS)
                    image.close()
                    image = resized
            finally:
                image.close()
    except Image.DecompressionBombError as exc:
        raise ImageInputError("图片尺寸超过安全解码上限，请提供较小图片或局部图片") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, TypeError, OverflowError) as exc:
        if isinstance(exc, ImageInputError):
            raise
        raise ImageInputError("图片内容损坏或无法解码，请重新上传完整图片") from exc
    raise ImageInputError("图片缩放后仍超过模型输入体积限制，请提供局部图片")


def image_data_url(path: str | Path) -> str:
    return prepare_image(path).url


def image_message_parts(paths: list[str | Path]) -> list[dict]:
    parts = []
    for index, path in enumerate(paths, 1):
        prepared = prepare_image(path)
        if prepared.note:
            parts.append({"type": "text", "text": f"[系统图片预处理，第 {index} 张] {prepared.note}"})
        parts.append({"type": "image_url", "image_url": {"url": prepared.url}})
    return parts
