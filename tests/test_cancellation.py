from __future__ import annotations

import sys
import threading
import time
from types import SimpleNamespace

import pytest

from umeko.cancellation import OperationCancelled, run_cancellable_process
from umeko.config import ModelConfig
from umeko.llm import client as client_module
from umeko.llm.client import LLMClient, _collect_stream


def _text_chunk(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(
            content=text, reasoning_content=None, tool_calls=None,
        ))]
    )


@pytest.mark.parametrize("proxy", [None, "http://127.0.0.1:7890"])
def test_llm_client_ignores_system_proxy_and_only_uses_configured_proxy(
    monkeypatch, proxy
):
    captured = {}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            captured["http"] = kwargs

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["openai"] = kwargs

    monkeypatch.setattr(client_module, "DefaultHttpxClient", FakeHttpClient)
    monkeypatch.setattr(client_module, "OpenAI", FakeOpenAI)

    client = LLMClient(ModelConfig(
        name="m", api_key="k", base_url="http://localhost/v1", proxy=proxy
    ))
    client._get_client()

    assert captured["http"]["proxy"] == proxy
    assert captured["http"]["trust_env"] is False


def test_collect_stream_assembles_content_and_tool_calls():
    chunks = [
        _text_chunk("你好"),
        _text_chunk("，世界"),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
            content=None, reasoning_content="想一下", tool_calls=None,
        ))]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
            content=None, reasoning_content=None,
            tool_calls=[SimpleNamespace(
                index=0, id="call_1",
                function=SimpleNamespace(name="read_document", arguments='{"pa'),
            )],
        ))]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
            content=None, reasoning_content=None,
            tool_calls=[SimpleNamespace(
                index=0, id=None,
                function=SimpleNamespace(name=None, arguments='th": "a.md"}'),
            )],
        ))]),
    ]
    resp = _collect_stream(iter(chunks))
    msg = resp.choices[0].message
    assert msg.content == "你好，世界"
    assert msg.reasoning_content == "想一下"
    assert msg.tool_calls[0].function.name == "read_document"
    assert msg.tool_calls[0].function.arguments == '{"path": "a.md"}'
    assert msg.tool_calls[0].model_dump()["function"]["arguments"] == '{"path": "a.md"}'


def test_collect_stream_honours_cancellation():
    def chunks():
        yield _text_chunk("a")
        yield _text_chunk("b")

    calls = iter([False, True])

    with pytest.raises(OperationCancelled):
        _collect_stream(chunks(), should_cancel=lambda: next(calls))


def test_run_cancellable_process_completes():
    result = run_cancellable_process(
        [sys.executable, "-c", "print('ok')"], encoding="utf-8"
    )
    assert result.returncode == 0
    assert "ok" in result.stdout


def test_run_cancellable_process_cancel_kills_tree():
    started = threading.Event()

    def sleeper():
        run_cancellable_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            should_cancel=started.is_set,
        )

    thread = threading.Thread(target=sleeper, daemon=True)
    thread.start()
    time.sleep(0.5)
    started.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
