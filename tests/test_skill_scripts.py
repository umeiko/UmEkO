"""Script discovery is read-only, scoped, bounded, and agrees with actual entrypoints."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from umeko.config import ModelConfig, Settings
from umeko.session import Session
from umeko.skills import build_file_tools
from umeko.skills.script_catalog import list_skill_script
from umeko.skills.script_runner import _resolve_script, run_skill_script
from umeko.server.admin import TEMPLATE_SCRIPT

ASSETS = Path(__file__).resolve().parents[1] / "umeko/builtin_skills"


@pytest.fixture
def library(tmp_path, monkeypatch):
    folder = tmp_path / "skills"
    shutil.copytree(ASSETS, folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    monkeypatch.setenv("UMEKO_SKILL_DIR", str(folder))
    return folder


def fixture_script(library, source):
    (library / "fixture").mkdir(exist_ok=True)
    (library / "fixture.md").write_text("---\nname: fixture\ndescription: Fixture\n---\nInstructions", encoding="utf-8")
    (library / "fixture/run.py").write_text(source, encoding="utf-8")


def test_builtin_contracts_and_helpers(library):
    items = json.loads(list_skill_script("drawio-flowchart"))["scripts"]
    declared = {i["script"]: i for i in items if i["documentation"] == "declared"}
    assert set(declared) == {"prepare_drawio.py", "generate_drawio.py"}
    assert next(i for i in items if i["script"] == "drawio_xml.py")["kind"] == "support_module"
    spec = declared["generate_drawio.py"]
    assert {"source_path", "xml", "formats", "style_path"} <= spec["input_schema"]["properties"].keys()
    assert spec["output_schema"]["properties"]["ok"]["type"] == "boolean"
    assert spec["outputs"] and json.loads(spec["invocation"]["arguments"]["args"]) == spec["example_args"]
    assert json.loads(list_skill_script("image-reasoning"))["scripts"] == []


def test_discovery_never_imports_or_executes_scripts(library, tmp_path):
    marker = tmp_path / "must-not-exist"
    fixture_script(library, f'from pathlib import Path\nPath({str(marker)!r}).write_text("executed")\n' + TEMPLATE_SCRIPT)
    # The executable statement is harmless to static analysis but would fail to parse
    # if prepended before an encoding/future directive; the template has neither.
    info = json.loads(list_skill_script("fixture", "run.py"))["scripts"][0]
    assert info["documentation"] == "declared"
    assert not marker.exists()
    fixture_script(library, f'SKILL_SCRIPT = __import__("pathlib").Path({str(marker)!r}).write_text("bad")')
    assert json.loads(list_skill_script("fixture"))["scripts"][0]["documentation"] == "invalid"
    assert not marker.exists()


def test_legacy_missing_and_malformed_contracts_are_explicit(library):
    fixture_script(library, '"""Legacy usage: takes JSON from stdin."""\nif __name__ == "__main__":\n    raise RuntimeError("do not execute")')
    item = json.loads(list_skill_script("fixture"))["scripts"][0]
    assert item["kind"] == "legacy_script" and item["input_schema"] is None
    assert "Legacy usage" in item["description"] and "warning" in item
    for source in ['SKILL_SCRIPT = []', 'SKILL_SCRIPT = {}', 'def broken(:']:
        fixture_script(library, source)
        assert json.loads(list_skill_script("fixture"))["scripts"][0]["documentation"] == "invalid"


@pytest.mark.parametrize("pack,script", [("../fixture", "run.py"), ("drawio-flowchart", "../run.py"),
                                          ("drawio-flowchart", "..\\run.py"), ("drawio-flowchart", "C:run.py"),
                                          ("drawio-flowchart", "unknown.py"), ("unknown", "")])
def test_invalid_paths_and_unknown_packages(library, pack, script):
    assert list_skill_script(pack, script).startswith("错误：")


def test_script_and_package_symlinks_rejected_in_discovery_and_execution(library):
    folder = library / "drawio-flowchart"
    try:
        (folder / "linked.py").symlink_to(library / "doc-image-qc/render_report.py")
    except OSError:
        pytest.skip("OS does not allow fixture symlinks")
    with pytest.raises(ValueError, match="链接"):
        _resolve_script("drawio-flowchart", "linked.py")
    assert list_skill_script("drawio-flowchart", "linked.py").startswith("错误：")
    assert run_skill_script("drawio-flowchart", "linked.py").startswith("错误：")
    (library / "linked.md").write_text("---\nname: linked\ndescription: Fixture\n---\nInstructions", encoding="utf-8")
    (library / "linked").symlink_to(folder, target_is_directory=True)
    assert list_skill_script("linked").startswith("错误：")


def test_pagination_and_size_limits(library):
    first = json.loads(list_skill_script("drawio-flowchart", limit=1))
    next_page = json.loads(list_skill_script("drawio-flowchart", offset=first["next_offset"], limit=1))
    assert first["scripts"][0]["script"] != next_page["scripts"][0]["script"]
    for kwargs in ({"offset": -1}, {"limit": 21}, {"offset": True}):
        assert list_skill_script("drawio-flowchart", **kwargs).startswith("错误：")
    fixture_script(library, "#" * (1024 * 1024 + 1))
    assert "1 MiB" in json.loads(list_skill_script("fixture"))["scripts"][0]["warning"]


def test_tool_checks_agent_skill_scope_and_does_not_load_body(library, tmp_path):
    session = Session(Settings(ModelConfig("fixture", "fixture-key", "http://unused.invalid")),
                      tmp_path / "generate", skill_dir=library, allowed_skill_packs={"doc-image-qc"})
    tools = {t.name: t for t in build_file_tools(session, SimpleNamespace(vision_enabled=False))}
    tool = tools["list_skill_script"]
    assert "未配置" in tool.handler(pack="drawio-flowchart")
    data = json.loads(tool.handler(pack="doc-image-qc"))
    assert data["scripts"][0]["script"] == "render_report.py"
    assert not session.active_skill_packs() and not session.output_dir.exists()


def test_template_metadata_and_actual_stdin_stdout_agree(library, tmp_path):
    fixture_script(library, TEMPLATE_SCRIPT)
    info = json.loads(list_skill_script("fixture", "run.py"))["scripts"][0]
    args = info["invocation"]["arguments"]
    result = run_skill_script(**args, workdir=tmp_path / "generate", session_root=tmp_path)
    assert "收到参数" in result and not result.startswith("错误：")


def test_builtin_examples_execute_with_declared_inputs(library, tmp_path):
    """Real subprocesses and fixture files; no provider, image inference or renderer."""
    import base64
    import re

    root = tmp_path / "session"
    workdir = root / "generate"
    workdir.mkdir(parents=True)
    (root / "attachments").mkdir()
    (root / "attachments/sample.png").write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))
    (workdir / "qc-report.json").write_text(json.dumps({"document": "sample", "items": [{
        "image": "attachments/sample.png", "status": "PASS", "checks": []}]}), encoding="utf-8")
    xml = re.search(r"```xml\n(.*?)```", (library / "drawio-flowchart/flowchart.md").read_text(encoding="utf-8"), re.S).group(1)
    (workdir / "approval-source.xml").write_text(xml, encoding="utf-8")
    for pack, script in [("drawio-flowchart", "prepare_drawio.py"), ("drawio-flowchart", "generate_drawio.py"),
                         ("doc-image-qc", "render_report.py")]:
        item = json.loads(list_skill_script(pack, script))["scripts"][0]
        result = run_skill_script(**item["invocation"]["arguments"], workdir=workdir, session_root=root)
        assert not result.startswith("错误："), result
    assert (workdir / "approval-task.md").is_file()
    assert (workdir / "approval.drawio").is_file()
    assert (workdir / "qc-report-sample.zip").is_file()
