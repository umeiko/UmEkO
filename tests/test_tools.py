"""文件工具：大文件上下文门禁、写沙箱、目录树兜底与过滤。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from umeko.skills import build_file_tools
from umeko.tree import TreeBudget, build_tree, compile_filter, render_text


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


# ---------- 目录树兜底与过滤 ----------

def _make_tree_fixture(base: Path) -> None:
    (base / "attachments").mkdir(parents=True)
    (base / "attachments" / "image-01.png").write_bytes(b"x" * 10)
    (base / "attachments" / "image-02.png").write_bytes(b"x" * 20)
    (base / "attachments" / "report.md").write_text("# r")
    (base / "workspace").mkdir()
    (base / "workspace" / "notes.txt").write_text("n")


def test_tree_filter_glob_and_regex(tmp_path):
    _make_tree_fixture(tmp_path)
    tree = build_tree(tmp_path, pattern="image-*")
    text = render_text(tree, max_level=2)
    assert "image-01.png" in text and "image-02.png" in text
    assert "report.md" not in text
    # 目录保留（可下钻）
    assert "workspace/" in text
    # 正则形态
    tree2 = build_tree(tmp_path, pattern=r"^image-\d+\.png$")
    text2 = render_text(tree2, max_level=2)
    assert "image-01.png" in text2 and "report.md" not in text2


def test_tree_filter_counts_omitted(tmp_path):
    _make_tree_fixture(tmp_path)
    tree = build_tree(tmp_path, pattern="image-*")
    attachments = next(c for c in tree.children if c.name == "attachments")
    # report.md 被滤掉，计入 omitted
    assert attachments.omitted == 1
    text = render_text(tree, max_level=2)
    assert "其余 1 项被折叠" in text


def test_tree_invalid_filter_raises():
    import pytest
    with pytest.raises(ValueError):
        compile_filter("(bad")


def test_tree_per_dir_cap(tmp_path):
    big = tmp_path / "many"
    big.mkdir()
    for i in range(80):
        (big / f"f{i:03}.txt").write_text("x")
    tree = build_tree(big)
    assert len(tree.children) == 50
    assert tree.omitted == 30
    text = render_text(tree, max_level=2)
    assert "其余 30 项被折叠" in text
    assert "f079.txt" not in text


def test_tree_total_budget(tmp_path):
    big = tmp_path / "deep"
    big.mkdir()
    for i in range(30):
        d = big / f"d{i:02}"
        d.mkdir()
        for j in range(10):
            (d / f"f{j}.txt").write_text("x")
    budget = TreeBudget(max_total=100)
    tree = build_tree(big, budget=budget)
    assert budget.truncated is True
    text = render_text(tree, max_level=2)
    assert "已截断" in text


def test_tree_depth_cap(tmp_path):
    p = tmp_path
    for i in range(30):
        p = p / f"lvl{i}"
    p.mkdir(parents=True)
    budget = TreeBudget(max_depth=5)
    tree = build_tree(tmp_path, budget=budget)
    text = render_text(tree, max_level=2)
    # 深层折叠，不展开
    assert "lvl29" not in text or "截断" in text or "折叠" in text


def test_list_dir_tool_filter(tmp_path):
    _make_tree_fixture(tmp_path)
    images = SimpleNamespace(pending=[], vision_enabled=False)
    tools = {s.name: s for s in build_file_tools(_session(tmp_path), images)}
    result = tools["list_dir"].handler(
        directory=".", filter="image-*", root=tmp_path
    )
    assert "image-01.png" in result
    assert "report.md" not in result
    # 非法过滤 → 错误信息（不抛异常）
    bad = tools["list_dir"].handler(directory=".", filter="(bad", root=tmp_path)
    assert bad.startswith("错误：")
