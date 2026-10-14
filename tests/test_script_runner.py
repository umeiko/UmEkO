"""Subprocess failures must reach the Agent tool result, not just progress cards."""
import pytest

from umeko.skills import script_runner


@pytest.fixture
def execute(tmp_path, monkeypatch):
    library = tmp_path / "library"
    pack = library / "fixture"
    pack.mkdir(parents=True)
    root = tmp_path / "session"
    workdir = root / "generate"
    workdir.mkdir(parents=True)
    monkeypatch.setattr(script_runner, "skill_packs_dir", lambda: library)
    def run(source, **kwargs):
        (pack / "fixture.py").write_text("import json,sys,time\n" + source, encoding="utf-8")
        return script_runner.run_skill_script("fixture", "fixture.py", workdir=workdir, session_root=root, **kwargs)
    return run


def test_nonzero_exit_cannot_claim_success_and_stderr_reaches_model(execute):
    progress = []
    response = execute('print("Traceback: renderer dependency missing", file=sys.stderr)\n'
                       'print(json.dumps({"ok":True,"result":"claimed success","files":["generate/draft.txt"]}))\n'
                       'sys.exit(7)', on_progress=progress.append)
    assert response.startswith("错误：") and "退出码 7" in response
    assert "renderer dependency missing" in response and "generate/draft.txt" in response
    assert progress == ["Traceback: renderer dependency missing"]


def test_failure_fields_and_partial_files_reach_model(execute):
    response = execute('print(json.dumps({"ok":False,"status":"partial","result":"draft ready",'
                       '"warnings":["PNG export failed"],"error":"renderer unavailable",'
                       '"files":["generate/draft.drawio"]}))')
    assert "部分失败" in response and "PNG export failed" in response
    assert "renderer unavailable" in response and "generate/draft.drawio" in response


@pytest.mark.parametrize("output", ["not JSON", "[]", '{"ok":"false"}', '{"ok":true,"files":{}}'])
def test_bad_protocol_reports_exit_and_stderr(execute, output):
    response = execute(f'print({output!r})\nprint("fixture diagnosis",file=sys.stderr)\nsys.exit(3)')
    assert response.startswith("错误：") and "fixture diagnosis" in response and "退出码：3" in response


def test_no_output_reports_stderr(execute):
    response = execute('print("ImportError: missing module",file=sys.stderr)\nsys.exit(2)')
    assert "无输出" in response and "ImportError: missing module" in response and "退出码：2" in response


def test_timeout_preserves_captured_diagnosis(execute):
    response = execute('print("renderer stalled after failure",file=sys.stderr,flush=True)\ntime.sleep(5)', timeout=1)
    assert "超时" in response and "renderer stalled after failure" in response


def test_success_keeps_warning_only_fields_visible(execute):
    response = execute('print("debug output")\nprint(json.dumps({"ok":True,"result":"completed",'
                       '"warnings":["optional dependency missing"],"files":[]}))')
    assert not response.startswith("错误：") and "completed" in response
    assert "optional dependency missing" in response
