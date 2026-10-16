"""Real gate/layout subprocesses with isolated skills and synthetic graph data."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys
from types import SimpleNamespace
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zlib

import pytest

from umeko.config import ModelConfig, Settings
from umeko.host.builtin_skills import ASSETS, install_builtin_skills
from umeko.host.storage import Store
from umeko.session import Session
from umeko.skills import build_file_tools
from umeko.skills.script_catalog import list_skill_script
from umeko.skills.script_runner import run_skill_script

XML = '''<mxfile><diagram name="Flow"><mxGraphModel><root>
<mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="a" value="提交" vertex="1" parent="1" style="rounded=1;fillColor=#2ECBFF;fontColor=#FFFFFF;strokeColor=none;">
<mxGeometry x="0" y="0" width="172" height="40" as="geometry"/></mxCell>
<mxCell id="b" value="审批" vertex="1" parent="1" style="rounded=1;fillColor=#2ECBFF;fontColor=#FFFFFF;strokeColor=none;">
<mxGeometry x="0" y="80" width="172" height="40" as="geometry"/></mxCell>
<mxCell id="e" value="提交后" edge="1" parent="1" source="a" target="b" style="edgeStyle=orthogonalEdgeStyle;endArrow=block;strokeColor=#666666;">
<mxGeometry relative="1" as="geometry"/></mxCell>
</root></mxGraphModel></diagram></mxfile>'''


@pytest.fixture
def context(tmp_path, monkeypatch):
    library = tmp_path / "skills"
    install_builtin_skills(Store(tmp_path / "data/db.sqlite"), library)
    monkeypatch.setenv("UMEKO_SKILL_DIR", str(library))
    root = tmp_path / "session"
    (root / "generate").mkdir(parents=True)
    (root / "attachments").mkdir()
    return library, root


def invoke(context, script, args):
    library, root = context
    process = subprocess.run([sys.executable, str(library / "drawio-correction/scripts" / script)],
        input=json.dumps({"args": args, "workdir": str(root / "generate"), "session_root": str(root)}, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8", timeout=15)
    result = json.loads(process.stdout)
    assert (process.returncode == 0) == result["ok"], process.stderr
    return result


def compressed_xml():
    model = ET.tostring(ET.fromstring(XML).find("diagram/mxGraphModel"), encoding="unicode")
    compressor = zlib.compressobj(wbits=-15)
    data = compressor.compress(quote(model).encode()) + compressor.flush()
    return "<mxfile><diagram>" + base64.b64encode(data).decode() + "</diagram></mxfile>"


@pytest.mark.parametrize("text,kind", [
    ("flowchart TD\nA[提交] --> B[审批]", "mermaid"),
    ("```mermaid\ngraph LR\nA --> B\n```", "mermaid"),
    (XML, "drawio"), (compressed_xml(), "drawio"),
    (ET.tostring(ET.fromstring(XML).find("diagram/mxGraphModel"), encoding="unicode"), "drawio"),
    ("1. 提交申请\n2. 审核；通过则归档，未通过返回修改", "markdown"),
    ("开始 → 提交 → 审批 → 结束", "markdown"),
])
def test_gate_accepts_only_bounded_flow_sources(context, text, kind):
    result = invoke(context, "prepare_correction.py", {"source_text": text})
    assert result["ok"] and result["status"] == "ready" and result["kind"] == kind
    assert all((context[1] / p).is_file() for p in result["files"])
    assert result["manifest_path"] in result["result"]
    assert not list((context[1] / "generate").glob("*.drawio"))


@pytest.mark.parametrize("text", [
    "写一个 Python 快排", "sequenceDiagram\nA->>B: hi", "# 一篇说明\n这是一般介绍",
    "![](attachments/figure.png)", "请处理 https://example.invalid/flow", "<xml/>",
    XML.replace('target="b"', 'target="missing"'),
    "1. 提交\n2. 审批\n" + "详细需求" * 600,
    "flowchart TD\n" + "A-->B\n" * 121,
    '<!DOCTYPE mxfile [<!ENTITY x "data">]>' + XML,
    "flowchart TD\nA[只有一个节点]",
    "```python\ndef process() -> int:\n    return 1\n```",
])
def test_gate_rejects_before_staging_conversion(context, text):
    result = invoke(context, "prepare_correction.py", {"source_text": text})
    assert not result["ok"] and result["status"] == "rejected"
    assert result["files"] == [] and result["error"]["code"] == "input_rejected"
    assert not list((context[1] / "generate").iterdir())


def test_file_gate_never_reads_binary_and_refuses_session_escape(context, tmp_path):
    root = context[1]
    (root / "attachments/image.png").write_bytes(b"not text")
    rejected = invoke(context, "prepare_correction.py", {"source_path": "attachments/image.png"})
    assert rejected["status"] == "rejected" and "文件类型" in rejected["result"]
    outside = tmp_path / "outside.md"
    outside.write_text("1. 提交\n2. 审批", encoding="utf-8")
    failed = invoke(context, "prepare_correction.py", {"source_path": "attachments/../../outside.md"})
    assert not failed["ok"] and not failed["files"]
    assert not list((root / "generate").iterdir())


@pytest.mark.parametrize("custom", [False, True])
def test_validated_file_and_xml_reuse_layout_and_custom_style_without_renderer(context, custom):
    library, root = context
    args = {"source_text": XML, "output_name": "approval"}
    if custom:
        (root / "attachments/style.md").write_text(
            '---\nname: custom\nbackground: "#FFFFFF"\nfont_family: Arial\nfont_size: 16\nedge_color: "#123456"\n---\n# 风格\n保留流程，字体 Arial。', encoding="utf-8")
        args["style_path"] = "attachments/style.md"
    prepared = invoke(context, "prepare_correction.py", args)
    (root / prepared["source_path"]).write_text(XML, encoding="utf-8")
    result = invoke(context, "finish_correction.py", {"manifest_path": prepared["manifest_path"], "return_xml": True})
    assert result["ok"] and result["files"] == ["generate/approval.drawio"]
    output = (root / result["files"][0]).read_text(encoding="utf-8")
    assert result["xml"] == output and output in result["result"]
    tree = ET.fromstring(output)
    assert tree.find("diagram/mxGraphModel").get("background") == ("#FFFFFF" if custom else "#F8F8F8")
    cell = tree.find('.//mxCell[@id="a"]')
    assert cell.get("value") == "提交" and cell.find("mxGeometry").get("height") is not None
    if custom:
        assert "fontSize=16" in cell.get("style") and "fontFamily=Arial" in cell.get("style")
        assert "strokeColor=#123456" in tree.find('.//mxCell[@id="e"]').get("style")
    assert not any((root / "generate").glob("*.png"))
    assert (library / "drawio-correction/scripts/drawio_flow.py").read_bytes() == (ASSETS / "drawio-flowchart/scripts/drawio_flow.py").read_bytes()
    assert (library / "drawio-correction/references/style.md").read_bytes() == (ASSETS / "drawio-flowchart/references/style.md").read_bytes()


@pytest.mark.parametrize("edited", [XML.replace('value="提交"', 'value="不同业务"'),
    XML.replace('value="提交后"', 'value="其他条件"'), XML.replace('source="a" target="b"', 'source="b" target="a"')])
def test_restyle_cannot_change_original_semantics(context, edited):
    prepared = invoke(context, "prepare_correction.py", {"source_text": XML})
    (context[1] / prepared["source_path"]).write_text(edited, encoding="utf-8")
    result = invoke(context, "finish_correction.py", {"manifest_path": prepared["manifest_path"]})
    assert not result["ok"] and "不得修改" in result["result"] and result["files"] == []
    assert not list((context[1] / "generate").glob("*.drawio"))


def test_shared_scripts_work_with_only_correction_skill_disclosed(context):
    library, root = context
    session = Session(Settings(ModelConfig("fixture", "fixture-key", "https://unused.invalid")),
                      root / "generate", skill_dir=library, allowed_skill_packs={"drawio-correction"})
    tools = {tool.name: tool for tool in build_file_tools(session, SimpleNamespace(vision_enabled=False))}
    assert "未配置" in tools["run_skill_script"].handler(pack="drawio-flowchart", script="generate_drawio.py", args="{}")
    data = json.loads(list_skill_script("drawio-correction", "prepare_correction.py"))
    assert data["scripts"][0]["documentation"] == "declared"
    response = tools["run_skill_script"].handler(pack="drawio-correction", script="prepare_correction.py",
        args=json.dumps({"source_text": "A → B"}))
    assert "门禁通过" in response and "manifest_path=generate/corrected-flowchart-job.json" in response
    rejected = run_skill_script("drawio-correction", "prepare_correction.py", json.dumps({"source_text": "写诗"}),
                              workdir=root / "generate", session_root=root)
    assert "input_rejected" in rejected and "未识别" in rejected


@pytest.mark.parametrize("custom", [False, True])
def test_shared_stock_upgrades_preserve_customizations_and_deletions(tmp_path, monkeypatch, custom):
    import umeko.host.builtin_skills as installer

    assets = tmp_path / "source"
    shutil.copytree(ASSETS, assets, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    monkeypatch.setattr(installer, "ASSETS", assets)
    store, library = Store(tmp_path / "db.sqlite"), tmp_path / "library"
    assert install_builtin_skills(store, library)
    target = library / "drawio-correction/references/style.md"
    if custom:
        target.write_text("# Administrator style", encoding="utf-8")
    (library / "drawio-correction/scripts/drawio_xml.py").unlink()
    source = assets / "drawio-flowchart/references/style.md"
    old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_text(source.read_text(encoding="utf-8") + "\nNew stock guidance\n", encoding="utf-8")
    manifest = assets / "stock-upgrades.json"
    upgrades = json.loads(manifest.read_text(encoding="utf-8"))
    upgrades["drawio-flowchart/style.md"] = [old_hash]
    manifest.write_text(json.dumps(upgrades), encoding="utf-8")
    assert install_builtin_skills(store, library)
    assert (library / "drawio-flowchart/references/style.md").read_bytes() == source.read_bytes()
    assert target.read_bytes() == (b"# Administrator style" if custom else source.read_bytes())
    assert not (library / "drawio-correction/scripts/drawio_xml.py").exists()
