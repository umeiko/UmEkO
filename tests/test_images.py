"""Real raster fixtures exercise the bytes sent to models, without model calls."""
import base64
from io import BytesIO
import os
import struct
import zlib

from PIL import Image
import pytest

from umeko import images
from umeko.llm import LLMClient


def save(path, fmt="PNG", size=(48, 32), mode="RGB", **options):
    with Image.new(mode, size, (120, 140, 160, 80) if mode == "RGBA" else "white") as image:
        image.save(path, format=fmt, **options)
    return path


def decoded(prepared):
    image = Image.open(BytesIO(prepared.data))
    image.load()
    return image


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP", "GIF", "BMP", "TIFF"])
@pytest.mark.parametrize("filename", ["upload", "wrong.txt", "wrong.jpg"])
def test_detects_actual_format_without_correct_extension_and_keeps_source(tmp_path, fmt, filename):
    path = save(tmp_path / filename, fmt)
    before = path.read_bytes()
    assert images.detect_image_format(path) == fmt
    assert images.validate_image(path) == path
    prepared = images.prepare_image(path)
    with decoded(prepared) as image:
        assert image.size == (48, 32)
        assert image.format in {"PNG", "JPEG", "WEBP"}
        assert prepared.url.startswith("data:" + Image.MIME[image.format] + ";base64,")
    assert base64.b64decode(prepared.url.split(",", 1)[1]) == prepared.data
    assert path.read_bytes() == before and list(tmp_path.iterdir()) == [path]
    if fmt in {"PNG", "JPEG", "WEBP"}:
        assert prepared.data == before and prepared.note == ""


def test_large_raster_shrinks_with_bounded_pixels_bytes_and_aspect_ratio(tmp_path):
    path = save(tmp_path / "large", "JPEG", size=(6000, 4000))
    before = path.read_bytes()
    prepared = images.prepare_image(path)
    with decoded(prepared) as image:
        assert max(image.size) <= images.MAX_IMAGE_EDGE
        assert image.width * image.height <= images.MAX_IMAGE_PIXELS
        assert abs(image.width / image.height - 1.5) < .002
    assert prepared.source_size == (6000, 4000)
    assert len(prepared.data) <= images.MAX_IMAGE_BYTES
    assert "等比缩小" in prepared.note
    assert path.read_bytes() == before


def test_large_file_is_compressed_instead_of_rejected_at_old_ten_mb_limit(tmp_path):
    path = save(tmp_path / "large-bitmap", "BMP", size=(2100, 1800))
    assert path.stat().st_size > 10 * 1024 * 1024
    assert images.validate_image(path) == path
    prepared = images.prepare_image(path)
    assert len(prepared.data) <= images.MAX_IMAGE_BYTES and prepared.format == "PNG"
    assert prepared.size == (2100, 1800)


def test_encoded_byte_budget_can_trigger_further_resize_without_losing_alpha(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "MAX_IMAGE_BYTES", 32 * 1024)
    path = tmp_path / "noise"
    with Image.frombytes("RGBA", (512, 512), os.urandom(512 * 512 * 4)) as image:
        image.save(path, format="PNG")
    prepared = images.prepare_image(path)
    assert len(prepared.data) <= 32 * 1024 and max(prepared.size) < 512
    with decoded(prepared) as image:
        assert image.mode == "RGBA" and image.format == "PNG"


def test_orientation_is_corrected_without_claiming_rotation_is_resize(tmp_path):
    exif = Image.Exif()
    exif[274] = 6
    path = save(tmp_path / "rotated", "JPEG", size=(400, 200), exif=exif)
    prepared = images.prepare_image(path)
    with decoded(prepared) as image:
        assert image.size == (200, 400) and image.getexif().get(274, 1) == 1
    assert "EXIF" in prepared.note and "缩小" not in prepared.note


def test_animation_sends_first_frame_and_tells_model_what_was_processed(tmp_path):
    path = tmp_path / "animation"
    with Image.new("RGB", (32, 24), "red") as first, Image.new("RGB", (32, 24), "blue") as second:
        first.save(path, format="GIF", save_all=True, append_images=[second], duration=100, loop=0)
    message = LLMClient.with_images([{"role": "user", "content": "Inspect"}], [path])[-1]
    assert "只分析第 1 帧/页" in message["content"][1]["text"]
    raw = base64.b64decode(message["content"][2]["image_url"]["url"].split(",", 1)[1])
    with Image.open(BytesIO(raw)) as image:
        assert image.format == "PNG" and image.convert("RGB").getpixel((0, 0)) == (255, 0, 0)


@pytest.mark.parametrize("payload", [b"not an image", b"%PDF-1.7\n", b"<svg></svg>", b"\x89PNG\r\n\x1a\n"])
def test_false_image_names_and_truncated_headers_fail_before_model_work(tmp_path, payload):
    path = tmp_path / "fake.png"
    path.write_bytes(payload)
    with pytest.raises(images.ImageInputError):
        images.validate_image(path)
    with pytest.raises(images.ImageInputError):
        LLMClient.with_images([{"role": "user", "content": "Inspect"}], [path])


def test_corrupt_png_checksums_and_truncated_jpeg_pixels_are_rejected(tmp_path):
    path = save(tmp_path / "broken", "PNG")
    data = bytearray(path.read_bytes())
    chunk = data.index(b"IDAT")
    length = struct.unpack(">I", data[chunk - 4:chunk])[0]
    data[chunk + 4 + length] ^= 1  # Corrupt pixel-data CRC, retaining signature.
    path.write_bytes(data)
    with pytest.raises(images.ImageInputError, match="损坏"):
        images.prepare_image(path)
    save(path, "JPEG", size=(64, 64))
    path.write_bytes(path.read_bytes()[:-20])
    with pytest.raises(images.ImageInputError, match="损坏"):
        images.prepare_image(path)


@pytest.mark.parametrize("size", [(9000, 9000), (65_537, 1), (100_000, 100_000)])
def test_header_pixel_bombs_rejected_before_decoding(tmp_path, monkeypatch, size):
    path = save(tmp_path / "bomb", "PNG", size=(1, 1))
    data = bytearray(path.read_bytes())
    data[16:24] = struct.pack(">II", *size)
    data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]))
    path.write_bytes(data)
    monkeypatch.setattr(Image.Image, "load", lambda *a, **kw: pytest.fail("pixel bomb decoded"))
    with pytest.raises(images.ImageInputError, match="安全解码上限"):
        images.prepare_image(path)


def test_source_byte_limit_is_enforced_before_decode(tmp_path, monkeypatch):
    path = save(tmp_path / "large", "PNG")
    monkeypatch.setattr(images, "MAX_INPUT_BYTES", 32)
    monkeypatch.setattr(Image, "open", lambda *a, **kw: pytest.fail("oversized source opened"))
    with pytest.raises(images.ImageInputError, match="源文件超过"):
        images.prepare_image(path)


def test_multimodal_payload_preserves_order_and_original_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "MAX_IMAGE_EDGE", 64)
    first = save(tmp_path / "first", "PNG", size=(200, 100))
    second = save(tmp_path / "second.bad", "JPEG")
    messages = [{"role": "user", "content": "Compare images"}]
    result = LLMClient.with_images(messages, [first, second])
    assert messages == [{"role": "user", "content": "Compare images"}]
    parts = result[-1]["content"]
    assert parts[0] == {"type": "text", "text": "Compare images"}
    assert "第 1 张" in parts[1]["text"] and "等比缩小" in parts[1]["text"]
    assert parts[2]["image_url"]["url"].startswith("data:image/png;")
    assert parts[3]["image_url"]["url"].startswith("data:image/jpeg;")
