"""文件工具：大文件上下文门禁、写沙箱。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from umeko.skills import build_file_tools


def _session(tmp_path: Path):
    return SimpleNamespace(
        output_dir=tmp_path,
        create_skill=lambda **kw: "ok",
        list_skill_packs=lambda **kw: "ok",
        use_skill=lambda **kw: "ok",
        read_working_doc=lambda **kw: "ok",
        write_working_doc=lambda **kw: "ok",
    )


def test_read_document_size_gate(tmp_path):
    """>20KB 的文件必须走子 Agent，主 Agent 只拿预览。"""
    big = tmp_path / "big.txt"
    big.write_text("大" * 30 * 1024, encoding="utf-8")
    images = SimpleNamespace(pending=[], vision_enabled=False)
    tools = {s.name: s for s in build_file_tools(_session(tmp_path), images)}
    result = tools["read_document"].handler(path=str(big))
    assert "文件过大" in result and "delegate_task" in result
    # 子 Agent 视角：force_read 直通
    sub_tools = {
        s.name: s
        for s in build_file_tools(_session(tmp_path), images, allow_force_read=True)
    }
    full = sub_tools["read_document"].handler(path=str(big), force_read=True)
    assert full.startswith("大") and len(full) >= 30 * 1024


def test_write_file_sandbox(tmp_path):
    """write_file 只允许写产物目录。"""
    images = SimpleNamespace(pending=[], vision_enabled=False)
    tools = {s.name: s for s in build_file_tools(_session(tmp_path), images)}
    outside = tmp_path.parent / "outside.txt"
    result = tools["write_file"].handler(path=str(outside), content="x")
    assert "只允许写入产物目录" in result
    ok = tools["write_file"].handler(path="note/a.md", content="hi")
    assert "已写入" in ok and (tmp_path / "note" / "a.md").read_text() == "hi"
