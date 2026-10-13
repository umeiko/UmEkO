from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

import pytest


REPO = Path(__file__).resolve().parents[1]
BUILTINS = REPO / "umeko" / "builtin_skills"
spec = importlib.util.spec_from_file_location("skillhub_packaging", REPO / "scripts/package_skillhub_skills.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


@pytest.fixture
def packages(tmp_path):
    source = tmp_path / "source"
    shutil.copytree(BUILTINS, source, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    config = source / "drawio-flowchart/config.json"
    data = json.loads(config.read_text(encoding="utf-8"))
    data["drawio_path"] = "C:/fixture-only/private/drawio.exe"
    config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    entry = source / "drawio-flowchart.md"
    entry.write_text(entry.read_text(encoding="utf-8") + "\n管理员自定义正文必须完整保留。\n", encoding="utf-8")
    snapshot = tmp_path / "snapshot"
    packager.export_skills(source, snapshot, "1.0.0")
    output = tmp_path / "release"
    archives = packager.package_skills(snapshot, output)
    return source, snapshot, output, archives


def run(pack, root, script, arguments):
    (root / "workspace").mkdir(parents=True, exist_ok=True)
    args_file = root / "workspace/arguments.json"
    args_file.write_text(json.dumps(arguments, ensure_ascii=False), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(pack / "scripts/run.py"), script, "--root", str(root), "--args-file", str(args_file)],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    return completed.returncode, json.loads(completed.stdout)


def test_complete_portable_reproducible_packages(packages, tmp_path):
    source, snapshot, output, archives = packages
    assert {p.stem for p in archives} == {"doc-image-qc", "drawio-flowchart", "image-reasoning"}
    for archive_path in archives:
        with zipfile.ZipFile(archive_path) as archive:
            assert archive.testzip() is None
            entry = archive.read("SKILL.md").decode("utf-8")
            fields = packager.validate_entry(entry)
            assert fields["slug"] == f"umeiko-{archive_path.stem}"
            original = source / f"{archive_path.stem}.md"
            assert packager.entry_parts(original.read_bytes().decode("utf-8"))[1].strip() in entry
            manifest = json.loads(archive.read("package-manifest.json"))
            assert manifest["source_files_sha256"][original.name] == packager.digest(original.read_bytes())
            for relative, data in packager.safe_files(source / archive_path.stem).items():
                if relative == "config.json" and archive_path.stem == "drawio-flowchart":
                    assert json.loads(archive.read(f"drawio-flowchart/{relative}"))["drawio_path"] == ""
                else:
                    assert archive.read(f"{archive_path.stem}/{relative}") == data
            if archive_path.stem == "drawio-flowchart":
                assert {"drawio-flowchart/linux-deployment.md", "drawio-flowchart/Dockerfile.linux.txt",
                        "drawio-flowchart/drawio_headless.sh", "drawio-flowchart/linux_smoke.py"} <= set(archive.namelist())
                assert not any(b"mermaid" in archive.read(member).lower() for member in archive.namelist())
    assert json.loads((source / "drawio-flowchart/config.json").read_text(encoding="utf-8"))["drawio_path"]
    second = packager.package_skills(snapshot, tmp_path / "repeat")
    assert [p.read_bytes() for p in archives] == [p.read_bytes() for p in second]
    checksums = (output / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert all(packager.digest(path.read_bytes()) in checksums for path in archives)


def test_packaged_runner_prepares_and_generates_both_diagram_types(packages, tmp_path):
    _, _, _, archives = packages
    pack = tmp_path / "unpacked"
    with zipfile.ZipFile(next(p for p in archives if p.stem == "drawio-flowchart")) as archive:
        archive.extractall(pack)
    root = tmp_path / "任务目录"
    (root / "attachments").mkdir(parents=True)
    (root / "attachments/需求.md").write_text("业务需求只在文件内读取", encoding="utf-8")
    code, prepared = run(pack, root, "prepare_drawio.py", {"document_paths": ["attachments/需求.md"], "diagram_type": "auto"})
    assert code == 0 and prepared["ok"]
    assert all((root / p).is_file() for p in prepared["files"])
    assert "architecture" in (root / prepared["files"][0]).read_text(encoding="utf-8")
    for kind in ("flowchart", "architecture"):
        rule = (pack / "drawio-flowchart" / f"{kind}.md").read_text(encoding="utf-8")
        xml = re.search(r"```xml\n(.*?)```", rule, re.S).group(1)
        (root / "generate/source.xml").write_text(xml, encoding="utf-8")
        code, result = run(pack, root, "generate_drawio.py", {"source_path": "generate/source.xml", "diagram_type": kind,
                                                            "output_name": kind, "formats": []})
        assert code == 0 and result["ok"]
        assert result["diagram_type"] == kind and not result["visual_review_performed"]
        xml = ET.parse(root / result["files"][0])
        assert any(c.get("vertex") == "1" for c in xml.iter("mxCell"))
    code, failed = run(pack, root, "generate_drawio.py", {"source_path": "generate/不存在.xml", "formats": []})
    assert code != 0 and not failed["ok"] and failed["files"] == []


def test_packaged_report_contains_inspected_image(packages, tmp_path):
    import base64

    _, _, _, archives = packages
    pack = tmp_path / "report-pack"
    with zipfile.ZipFile(next(p for p in archives if p.stem == "doc-image-qc")) as archive:
        archive.extractall(pack)
    root = tmp_path / "report-task"
    (root / "attachments").mkdir(parents=True)
    (root / "generate").mkdir()
    (root / "attachments/sample.png").write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))
    report = {"document": "image-inspection", "items": [{"image": "attachments/sample.png", "status": "PASS",
               "checks": [{"id": "C1", "name": "图文一致", "status": "NA", "note": "没有正文参照"}]}]}
    (root / "generate/qc-report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    code, result = run(pack, root, "render_report.py", {"data_path": "generate/qc-report.json", "doc_dir": ""})
    assert code == 0 and result["ok"]
    assert all((root / relative).is_file() for relative in result["files"])
    with zipfile.ZipFile(root / next(p for p in result["files"] if p.endswith(".zip"))) as archive:
        assert archive.testzip() is None
        assert "attachments/sample.png" in archive.namelist()
        assert any(p.endswith(".html") for p in archive.namelist())


def test_manifest_detects_unreviewed_modification(packages, tmp_path):
    _, snapshot, _, _ = packages
    entry = snapshot / "image-reasoning/SKILL.md"
    entry.write_text(entry.read_text(encoding="utf-8") + "\n未经审核的编辑。\n", encoding="utf-8")
    with pytest.raises(ValueError, match="快照清单不匹配"):
        packager.package_skills(snapshot, tmp_path / "invalid")


def test_rejects_binary_members_and_keeps_existing_snapshot(packages, tmp_path):
    source, snapshot, _, _ = packages
    with pytest.raises(ValueError, match="目标已经存在"):
        packager.export_skills(source, snapshot, "1.0.1")
    (source / "drawio-flowchart/tool.exe").write_bytes(b"MZ\0")
    with pytest.raises(ValueError, match="不支持的文件类型"):
        packager.export_skills(source, tmp_path / "invalid-export", "1.0.0")
