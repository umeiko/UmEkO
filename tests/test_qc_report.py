from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import quote
import zipfile

import pytest

from umeko.host.builtin_agents import ASSETS


@pytest.fixture
def renderer(tmp_path):
    pack = tmp_path / "doc-image-qc"
    shutil.copytree(ASSETS / "doc-image-qc", pack)
    spec = importlib.util.spec_from_file_location("qc_report_fixture", pack / "render_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_matrix_and_offline_legend_explain_checks_and_statuses(renderer):
    report = {"items": [
        {"image": "one.png", "status": "WARN", "checks": [
            {"id": "C1", "status": "NA", "note": "没有正文"},
            {"id": "C2", "status": "WARN", "note": "文字模糊"},
            {"id": "U1", "status": "PASS"},
            {"id": "U2", "status": "NA", "note": "没有真实界面参照"},
        ]},
        {"image": "two.png", "status": "PASS", "checks": [{"id": "C2", "status": "PASS"}]},
    ]}
    rendered = renderer.render_report_html(report)
    for cid, name in {"C1": "图文一致性", "C2": "图片质量", "U1": "界面截图正确性", "U2": "界面-实际一致性"}.items():
        assert f'<span class="check-id">{cid}</span><span class="check-name">{name}</span>' in rendered
        assert f'<code>{cid}</code>{name}' in rendered
        assert f'<option value="{cid}">{cid} · {name}</option>' in rendered
    assert "通用检查项（所有图片）" in rendered and "界面截图类" in rendered
    assert "图片内容与文中临近描述是否一致" in rendered
    assert "清晰度、文字可读性、构图完整性" in rendered
    assert "界面内容与真实产品界面核对" in rendered
    assert "模型能力待验证" in rendered
    assert "数字是类别内的序号，不是评分" in rendered
    assert "NA：未检查" in rendered and "—：本图未列入该项检查" in rendered
    assert '<span class="cell NA">NA</span>' in rendered
    assert '<span class="cell absent">—</span>' in rendered
    assert "NA 和 — 均不表示通过" in rendered
    assert '<details class="check-legend" open>' in rendered
    assert '<tbody><tr data-img="one.png">' in rendered  # Filter JavaScript selects tbody rows.
    assert "S1" not in rendered and "N1" not in rendered  # Only the report's checks are listed.


def test_custom_checklist_is_the_source_and_is_html_escaped(renderer):
    Path(renderer.__file__).with_name("checks.md").write_text(
        "## 自定义检查\n\n| 编号 | 检查项 | 说明 | 备注 |\n|---|---|---|---|\n"
        '| C1 | 新的检查名称 | 比较 **标签** `a\\|b` 与 <script>alert(1)</script> | "谨慎" & 复核 |\n',
        encoding="utf-8",
    )
    rendered = renderer.render_report_html({"items": [{
        "image": "one.png", "status": "PASS", "checks": [{"id": "C1", "status": "PASS"}],
    }]})
    assert "新的检查名称" in rendered and "自定义检查" in rendered
    assert "比较 标签 a|b 与 &lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "&quot;谨慎&quot; &amp; 复核" in rendered
    assert "图片内容与文中临近描述是否一致" not in rendered
    assert "<script>alert(1)</script>" not in rendered


def test_report_can_supply_custom_names_and_scopes_without_a_checklist(renderer):
    Path(renderer.__file__).with_name("checks.md").unlink()
    rendered = renderer.render_report_html({"items": [{
        "image": "one.png", "status": "PASS", "checks": [
            {"id": "X1", "name": 'Custom "check"', "description": "Inspect <labels>", "status": "PASS"},
            {"id": "UNKNOWN", "status": "NA"},
        ],
    }]})
    assert "Custom &quot;check&quot;" in rendered
    assert "Inspect &lt;labels&gt;" in rendered
    assert "未命名检查项" in rendered and "未提供检查范围" in rendered
    assert "图文一致性" not in rendered  # No invented meaning for an unknown identifier.


def test_legacy_reports_without_check_ids_still_render(renderer):
    rendered = renderer.render_report_html({"items": [{
        "image": "one.png", "status": "WARN", "quality": "文字模糊",
    }]})
    assert "文字模糊" in rendered
    assert '<details class="check-legend"' not in rendered
    assert '<table class="matrix">' not in rendered


def run_report(renderer, root, report, doc_dir):
    generate = root / "generate"
    generate.mkdir(parents=True, exist_ok=True)
    source = generate / "qc-report.json"
    source.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    payload = {"workdir": str(generate), "session_root": str(root), "args": {
        "data_path": "generate/qc-report.json", "doc_dir": doc_dir,
    }}
    completed = subprocess.run([sys.executable, renderer.__file__], input=json.dumps(payload),
                               capture_output=True, text=True, encoding="utf-8", check=True)
    result = json.loads(completed.stdout)
    assert result["ok"], result
    assert json.loads(source.read_text(encoding="utf-8")) == report  # Input conclusions stay untouched.
    return generate, result


@pytest.mark.parametrize("doc_dir", ["", "workspace/docs"])
def test_zip_and_html_include_pasted_attachments_with_document_images(renderer, tmp_path, doc_dir):
    root = tmp_path / "session"
    paths = {
        "attachments/图 #1.png": b"pasted screenshot",
        "workspace/docs/images/图 #1.png": b"document screenshot with the same name",
        "workspace/shared/ref.png": b"shared reference",
        "generate/chart.png": b"generated chart",
        "attachments/bare.png": b"old report pasted basename",
        "attachments/windows.png": b"windows relative path",
        "attachments/unused.png": b"unrelated attachment",
    }
    for relative, content in paths.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    references = [
        "attachments/图 #1.png",
        str(root / "attachments/图 #1.png"),  # Absolute paths provided to the model also work.
        "images/图 #1.png" if doc_dir else "workspace/docs/images/图 #1.png",
        "../shared/ref.png" if doc_dir else "workspace/shared/ref.png",
        "generate/chart.png",
        "bare.png",
        "attachments\\windows.png",
    ]
    report = {"document": "mixed", "items": [
        {"image": src, "status": "PASS", "checks": [{"id": "C2", "status": "PASS"}]} for src in references
    ]}
    generate, result = run_report(renderer, root, report, doc_dir)
    assert "未打包" not in result["result"]
    exported = json.loads((generate / "qc-report-mixed.json").read_text(encoding="utf-8"))
    assert exported["packaging"] == {"packed_images": 6, "missing_images": []}
    assert exported["items"][0]["image"] == exported["items"][1]["image"] == "attachments/图 #1.png"
    html = (generate / "qc-report-mixed.html").read_text(encoding="utf-8")
    with zipfile.ZipFile(generate / "qc-report-mixed.zip") as archive:
        expected = set(paths) - {"attachments/unused.png"}
        assert set(archive.namelist()) == expected | {"qc-report.html", "qc-report.json"}
        zipped_html = archive.read("qc-report.html").decode()
        assert json.loads(archive.read("qc-report.json")) == exported
        for relative in expected:
            assert archive.read(relative) == paths[relative]
            assert f'src="{quote(relative, safe="/")}"' in zipped_html
            assert f'src="{quote("../" + relative, safe="/")}"' in html
    # Re-render the exported canonical JSON with the original document directory.
    rerendered, assets = renderer._prepare_images(exported, root / doc_dir, root)
    assert rerendered["packaging"] == exported["packaging"]
    assert set(assets) == expected


def test_missing_or_outside_images_are_reported_in_tool_result_and_html(renderer, tmp_path):
    root = tmp_path / "session"
    (root / "workspace/docs").mkdir(parents=True)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"must never be packaged")
    private = root / "client/private.png"
    private.parent.mkdir()
    private.write_bytes(b"private session state")
    references = ["attachments/deleted.png", str(outside), str(private), "../../../outside.png"]
    report = {"document": "missing", "items": [{"image": src, "status": "PASS"} for src in references]}
    generate, result = run_report(renderer, root, report, "workspace/docs")
    assert "图片未打包" in result["result"]
    assert "deleted.png" in result["result"] and "路径无效或超出" in result["result"]
    html = (generate / "qc-report-missing.html").read_text(encoding="utf-8")
    assert "图片未完整打包 · 4 张" in html
    assert '<div class="asset-warning">' in html
    assert "文件不存在" in html
    assert '<div class="thumb"><img' not in html  # Do not render unsafe or missing src URLs.
    with zipfile.ZipFile(generate / "qc-report-missing.zip") as archive:
        assert set(archive.namelist()) == {"qc-report.html", "qc-report.json"}
        assert b"must never be packaged" not in archive.read("qc-report.json")


def test_symlink_image_outside_session_is_not_packaged(renderer, tmp_path):
    root = tmp_path / "session"
    (root / "attachments").mkdir(parents=True)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside image")
    link = root / "attachments/link.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Creating a symlink requires privileges on this platform")
    report, assets = renderer._prepare_images({"items": [{"image": "attachments/link.png"}]}, root, root)
    assert not assets
    assert report["packaging"]["missing_images"]

