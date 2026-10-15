"""Subprocess failures must reach the Agent tool result, not just progress cards."""
import json

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
    assert "超时" in response and "renderer stalled after failure" in response and "SCRIPT_TIMEOUT" in response


def test_success_keeps_warning_only_fields_visible(execute):
    response = execute('print("debug output")\nprint(json.dumps({"ok":True,"result":"completed",'
                       '"warnings":["optional dependency missing"],"files":[]}))')
    assert not response.startswith("错误：") and "completed" in response
    assert "optional dependency missing" in response


def declared(schema, *, example=None):
    spec = {"description": "Fixture transformation", "usage": "Pass the declared args object.",
            "input_schema": {"type": "object", **schema}, "outputs": ["stdout result"],
            "example_args": example or {}}
    return "SKILL_SCRIPT = " + repr(spec) + "\n"


@pytest.mark.parametrize("arguments,code", [
    ("{broken", "SCRIPT_ARGUMENT_JSON"), ("{\"value\":NaN}", "SCRIPT_ARGUMENT_JSON"),
    ("[]", "SCRIPT_ARGUMENT_TYPE"), ("null", "SCRIPT_ARGUMENT_TYPE"),
    ("false", "SCRIPT_ARGUMENT_TYPE"), ('"nested JSON string"', "SCRIPT_ARGUMENT_TYPE"),
    ({"value": "not encoded"}, "SCRIPT_ARGUMENT_TYPE"),
])
def test_argument_envelope_errors_never_launch_script(execute, monkeypatch, arguments, code):
    monkeypatch.setattr(script_runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("invalid args executed a script"))
    result = execute('raise RuntimeError("must not run")', args=arguments)
    assert code in result and "脚本尚未执行" in result and "args" in result
    assert "请确保路径正确" not in result


@pytest.mark.parametrize("schema,arguments,expected", [
    ({"required": ["source_path"], "properties": {"source_path": {"type": "string"}}}, {}, "args.source_path"),
    ({"properties": {"formats": {"type": "array"}}}, {"formats": "png"}, "期望 array，实际为 string"),
    ({"properties": {"kind": {"enum": ["diagram", "report"]}}}, {"kind": "other"}, "允许"),
    ({"additionalProperties": False, "properties": {"data_path": {"type": "string"}}}, {"path": "workspace/input.json"}, "未知字段：path"),
    ({"properties": {"paths": {"type": "array", "items": {"type": "string"}}}}, {"paths": ["workspace/a.txt", 42]}, "args.paths[1]"),
    ({"anyOf": [{"required": ["source_path"]}, {"required": ["xml"]}]}, {}, "args.source_path或args.xml"),
    ({"properties": {"width": {"type": "number", "exclusiveMinimum": 0}}}, {"width": -1}, "exclusiveMinimum"),
])
def test_declared_schema_reports_specific_fields_without_side_effects(execute, monkeypatch, schema, arguments, expected):
    monkeypatch.setattr(script_runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("schema rejection started a process"))
    source = declared(schema, example={"source_path": "workspace/sample.xml"}) + 'raise RuntimeError("must not run")'
    result = execute(source, args=json.dumps(arguments))
    assert "SCRIPT_ARGUMENT_INVALID" in result and expected in result
    assert "脚本尚未执行" in result and "list_skill_script" in result and "args 示例" in result


def test_contract_schema_errors_are_not_reported_as_bad_caller_paths(execute, monkeypatch):
    monkeypatch.setattr(script_runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("bad contract executed"))
    result = execute(declared({"required": "must be array"}), args="{}")
    assert "SCRIPT_CONTRACT_INVALID" in result and "input_schema" in result and "管理员" in result
    result = execute('def broken(:')
    assert "SCRIPT_SYNTAX_ERROR" in result and "语法错误" in result


def test_local_schema_refs_work_but_remote_refs_are_never_fetched(execute, monkeypatch):
    schema = {"$defs": {"path": {"type": "string"}}, "properties": {"input": {"$ref": "#/$defs/path"}}}
    source = declared(schema) + 'print(json.dumps({"ok":True,"result":"validated","files":[]}))'
    assert execute(source, args='{"input":"workspace/input.txt"}') == "validated"
    monkeypatch.setattr(script_runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("remote ref executed"))
    remote = {"properties": {"input": {"$ref": "https://example.invalid/schema"}}}
    result = execute(declared(remote), args='{"input":"fixture"}')
    assert "SCRIPT_CONTRACT_INVALID" in result and "引用无法解析" in result


def test_validation_does_not_inject_defaults_or_echo_argument_values(execute):
    schema = {"properties": {"message": {"type": "string", "default": "fixture-default"}}}
    source = declared(schema) + 'print(json.dumps({"ok":True,"result":json.dumps(json.load(sys.stdin)["args"]),"files":[]}))'
    assert execute(source, args="{}") == "{}"
    result = execute(source, args='{"message":{"secret":"fixture-do-not-echo"}}')
    assert "args.message" in result and "fixture-do-not-echo" not in result


def test_dependency_tracebacks_and_structured_script_failures_are_distinct(execute):
    result = execute('print("ModuleNotFoundError: No module named fixture_dependency",file=sys.stderr)\nsys.exit(1)')
    assert "SCRIPT_DEPENDENCY_MISSING" in result and "fixture_dependency" in result and "管理员" in result
    result = execute('print("ImportError: cannot import name fixture_symbol",file=sys.stderr)\nsys.exit(1)')
    assert "SCRIPT_DEPENDENCY_ERROR" in result and "fixture_symbol" in result
    result = execute('print(json.dumps({"ok":False,"status":"partial","result":"Draft retained",'
                     '"files":["generate/draft.txt"],"error":{"code":"INPUT_DATA_INVALID",'
                     '"field":"args.data_path","message":"Missing items array in input JSON",'
                     '"hint":"Add items to the input file"}}))')
    assert "INPUT_DATA_INVALID" in result and "字段：args.data_path" in result
    assert "修正建议：Add items" in result and "generate/draft.txt" in result and "部分失败" in result


def test_no_arguments_or_error_contract_is_fabricated_for_legacy_scripts(execute):
    source = 'print(json.dumps({"ok":False,"result":"Fixture business check failed","files":[]}))'
    result = execute(source, args='{"legacy_option":17}')
    assert "SCRIPT_REPORTED_FAILURE" in result and "Fixture business check failed" in result
    assert "SCRIPT_ARGUMENT_INVALID" not in result and "请确保路径正确" not in result
