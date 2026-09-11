"""DSML 文本工具调用解析（dmxapi deepseek 类网关怪癖）。"""

from types import SimpleNamespace

from umeko.llm.client import _normalize_dsml, _parse_dsml_tool_calls, message_text

DSML = (
    '\n\n<｜DSML｜tool_calls>\n<｜DSML｜invoke name="write_file">\n'
    '<｜DSML｜parameter name="path" string="true">hello.md</｜DSML｜parameter>\n'
    '<｜DSML｜parameter name="content" string="true">你好</｜DSML｜parameter>\n'
    '<｜DSML｜parameter name="count">3</｜DSML｜parameter>\n'
    "</｜DSML｜invoke>\n</｜DSML｜tool_calls>"
)


def test_parse_dsml():
    calls, cleaned = _parse_dsml_tool_calls(DSML)
    assert cleaned == ""
    assert len(calls) == 1
    fn = calls[0].function
    assert fn.name == "write_file"
    import json

    args = json.loads(fn.arguments)
    assert args == {"path": "hello.md", "content": "你好", "count": 3}
    assert calls[0].model_dump()["function"]["name"] == "write_file"


def test_normalize_moves_reasoning_dsml_to_tool_calls():
    msg = SimpleNamespace(content="", reasoning_content=DSML, tool_calls=None)
    resp = SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    out = _normalize_dsml(resp)
    m = out.choices[0].message
    assert m.tool_calls and m.tool_calls[0].function.name == "write_file"
    assert m.reasoning_content is None  # DSML 块已从文本剥离


def test_normalize_keeps_structured_calls():
    existing = SimpleNamespace(function=SimpleNamespace(name="x", arguments="{}"))
    msg = SimpleNamespace(content="hi", reasoning_content=None, tool_calls=[existing])
    resp = SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    out = _normalize_dsml(resp)
    assert out.choices[0].message.tool_calls == [existing]


def test_message_text_fallback():
    msg = SimpleNamespace(content="", reasoning_content="正文在这里", tool_calls=None)
    assert message_text(msg) == "正文在这里"
    msg2 = SimpleNamespace(content="正式内容", reasoning_content="思考", tool_calls=None)
    assert message_text(msg2) == "正式内容"
