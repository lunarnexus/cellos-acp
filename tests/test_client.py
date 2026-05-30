"""Tests for cellos-acp core client."""

import asyncio
import json
import pytest
from types import SimpleNamespace


# ── Result dataclass ────────────────────────────────────────────────


def test_result_combined_text():
    from cellos_acp.result import AcpRunResult

    assert AcpRunResult(text="hello", thinking="thinking...").combined_text == "hello"
    assert AcpRunResult(text="", thinking="only thinking").combined_text == "only thinking"


def test_result_success():
    from cellos_acp.result import AcpRunResult

    assert AcpRunResult(text="ok").success is True
    assert AcpRunResult(error=ValueError("fail")).success is False
    assert AcpRunResult(text="ok", session_id="ses_1", timeout=False).success is True


def test_result_defaults():
    from cellos_acp.result import AcpRunResult

    r = AcpRunResult(text="ok")
    assert r.session_id is None
    assert r.message_id is None
    assert r.started_at is None
    assert r.completed_at is None
    assert r.last_event_at is None
    assert r.last_event_type is None
    assert r.timeout is False
    assert r.aborted is False
    assert r.error_type is None


def test_tool_call_record():
    from cellos_acp.result import ToolCallRecord

    rec = ToolCallRecord(tool_call_id="tc_1", title="task")
    assert rec.started_at is None
    assert rec.updated_at is None
    assert rec.nested_session_id is None

    rec2 = ToolCallRecord(
        tool_call_id="tc_1",
        title="task",
        started_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:01Z",
        nested_session_id="ses_nested",
    )
    assert rec2.nested_session_id == "ses_nested"


# ── Registry ────────────────────────────────────────────────────────


def test_registry_get_known():
    from cellos_acp.registry import get_adapter

    adapter = get_adapter("opencode")
    assert adapter.name == "opencode"
    assert adapter.command == "opencode"
    assert "acp" in adapter.args


def test_registry_get_unknown():
    from cellos_acp.registry import get_adapter

    with pytest.raises(KeyError):
        get_adapter("nonexistent")


def test_registry_list():
    from cellos_acp.registry import _registry

    names = _registry.list_names()
    assert "opencode" in names
    assert len(names) >= 3


# ── EventCollector: text / thinking ────────────────────────────────


def test_event_collector_separates_text_and_thinking():
    from cellos_acp.client import _EventCollector
    from acp.schema import AgentMessageChunk, AgentThoughtChunk, TextContentBlock

    collector = _EventCollector()
    collector.on_message_chunk(
        AgentMessageChunk(
            content=TextContentBlock(type="text", text="msg"),
            session_update="agent_message_chunk",
        )
    )
    collector.on_thought_chunk(
        AgentThoughtChunk(
            content=TextContentBlock(type="text", text="thought"),
            session_update="agent_thought_chunk",
        )
    )
    result = collector.to_result()
    assert result.text == "msg"
    assert result.thinking == "thought"


# ── EventCollector: diagnostics ────────────────────────────────────


def test_collector_stores_session_and_message_ids():
    from cellos_acp.client import _EventCollector

    collector = _EventCollector()
    collector.session_id = "ses_test"
    collector.message_id = "msg_test"
    collector.started_at = "2026-01-01T00:00:00Z"
    result = collector.to_result()
    assert result.session_id == "ses_test"
    assert result.message_id == "msg_test"
    assert result.started_at == "2026-01-01T00:00:00Z"


def test_collector_tracks_last_event_type_and_time():
    from cellos_acp.client import _EventCollector
    from acp.schema import AgentMessageChunk, TextContentBlock

    collector = _EventCollector()
    collector.on_message_chunk(
        AgentMessageChunk(
            content=TextContentBlock(type="text", text="hello"),
            session_update="agent_message_chunk",
        )
    )
    assert collector.last_event_type == "AgentMessageChunk"
    assert collector.last_event_at is not None


def test_collector_updates_previews():
    from cellos_acp.client import _EventCollector
    from acp.schema import AgentMessageChunk, AgentThoughtChunk, TextContentBlock

    collector = _EventCollector()
    collector.on_message_chunk(
        AgentMessageChunk(
            content=TextContentBlock(type="text", text="hello world"),
            session_update="agent_message_chunk",
        )
    )
    collector.on_thought_chunk(
        AgentThoughtChunk(
            content=TextContentBlock(type="text", text="thinking deeply"),
            session_update="agent_thought_chunk",
        )
    )
    result = collector.to_result()
    assert "hello world" in result.last_message_preview
    assert "thinking deeply" in result.last_thought_preview


def test_collector_previews_are_bounded():
    from cellos_acp.client import _EventCollector
    from acp.schema import AgentMessageChunk, AgentThoughtChunk, TextContentBlock

    collector = _EventCollector()
    long_text = "x" * 2000
    collector.on_message_chunk(
        AgentMessageChunk(
            content=TextContentBlock(type="text", text=long_text),
            session_update="agent_message_chunk",
        )
    )
    collector.on_thought_chunk(
        AgentThoughtChunk(
            content=TextContentBlock(type="text", text=long_text),
            session_update="agent_thought_chunk",
        )
    )
    result = collector.to_result()
    assert len(result.last_message_preview) <= 500
    assert len(result.last_thought_preview) <= 500


def test_collector_completed_at_in_result():
    from cellos_acp.client import _EventCollector

    collector = _EventCollector()
    collector.completed_at = "2026-01-01T00:00:05Z"
    result = collector.to_result()
    assert result.completed_at == "2026-01-01T00:00:05Z"


# ── EventCollector: tool calls ─────────────────────────────────────


def test_tool_start_creates_active_tool_call():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart

    collector = _EventCollector()
    collector.on_tool_start(
        ToolCallStart(
            tool_call_id="tc_1",
            title="task",
            raw_input={"arg": "val"},
            session_update="tool_call",
        )
    )
    result = collector.to_result()
    assert len(result.active_tool_calls) == 1
    assert result.active_tool_calls[0].tool_call_id == "tc_1"


def test_tool_progress_terminal_removes_from_active():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.on_tool_start(
        ToolCallStart(tool_call_id="tc_1", title="task", raw_input={}, session_update="tool_call")
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1", status="completed", raw_output={"result": "done"}, session_update="tool_call_update"
        )
    )
    result = collector.to_result()
    assert len(result.active_tool_calls) == 0
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].status == "completed"


def test_tool_progress_non_terminal_keeps_active():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.on_tool_start(
        ToolCallStart(tool_call_id="tc_1", title="task", raw_input={}, session_update="tool_call")
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1", status="in_progress", raw_output={"partial": "output"}, session_update="tool_call_update"
        )
    )
    result = collector.to_result()
    assert len(result.active_tool_calls) == 1


# ── EventCollector: nested session ID extraction ───────────────────


def test_nested_session_id_extracted_from_metadata():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.on_tool_start(
        ToolCallStart(tool_call_id="tc_1", title="task", raw_input={}, session_update="tool_call")
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1", status="in_progress", raw_output={"metadata": {"sessionId": "ses_nested"}}, session_update="tool_call_update"
        )
    )
    result = collector.to_result()
    assert result.tool_calls[0].nested_session_id == "ses_nested"


def test_nested_session_id_deeply_nested():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.on_tool_start(
        ToolCallStart(tool_call_id="tc_1", title="task", raw_input={}, session_update="tool_call")
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1", status="in_progress", raw_output={"data": {"nested": {"session_id": "deep_ses"}}}, session_update="tool_call_update"
        )
    )
    result = collector.to_result()
    assert result.tool_calls[0].nested_session_id == "deep_ses"


def test_nested_session_id_in_raw_input():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart

    collector = _EventCollector()
    collector.on_tool_start(
        ToolCallStart(tool_call_id="tc_1", title="task", raw_input={"nested_session_id": "from_input"}, session_update="tool_call")
    )
    result = collector.to_result()
    assert result.tool_calls[0].nested_session_id == "from_input"


# ── EventCollector: timeout state preservation ─────────────────────


def test_timeout_preserves_partial_state():
    from cellos_acp.client import _EventCollector
    from acp.schema import AgentThoughtChunk, ToolCallStart, ToolCallProgress, TextContentBlock

    collector = _EventCollector()
    collector.session_id = "ses_test"
    collector.message_id = "msg_test"
    collector.started_at = "2026-01-01T00:00:00Z"
    collector.on_thought_chunk(
        AgentThoughtChunk(content=TextContentBlock(type="text", text="thinking"), session_update="agent_thought_chunk")
    )
    collector.on_tool_start(
        ToolCallStart(tool_call_id="tc_1", title="task", raw_input={}, session_update="tool_call")
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1", status="in_progress", raw_output={"metadata": {"sessionId": "ses_nested"}}, session_update="tool_call_update"
        )
    )

    result = collector.to_result()
    result.timeout = True
    result.error_type = "TimeoutError"
    result.error_message = "timed out"
    result.completed_at = "2026-01-01T00:00:05Z"

    assert result.timeout is True
    assert result.session_id == "ses_test"
    assert len(result.active_tool_calls) == 1
    assert result.active_tool_calls[0].nested_session_id == "ses_nested"


# ── EventCollector: structured results ─────────────────────────────


def test_collector_captures_structured_result_for_required_tool():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.set_required_output_tool("cellos_submit_reply")
    collector.on_tool_start(
        ToolCallStart(tool_call_id="tc_1", title="cellos_submit_reply", raw_input={"summary": "done"}, session_update="tool_call")
    )
    collector.on_tool_progress(
        ToolCallProgress(tool_call_id="tc_1", title="cellos_submit_reply", status="completed", raw_output={"summary": "done"}, session_update="tool_call_update")
    )

    result = collector.to_result()
    assert result.structured_result is not None
    assert result.structured_result.kind == "cellos_submit_reply"
    assert result.structured_result.data["summary"] == "done"


def test_collector_captures_structured_result_for_prefixed_tool_title():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.set_required_output_tool("cellos_submit_reply")
    collector.on_tool_start(
        ToolCallStart(tool_call_id="tc_1", title="cellos-result-tools_cellos_submit_reply", raw_input={"summary": "done"}, session_update="tool_call")
    )
    collector.on_tool_progress(
        ToolCallProgress(tool_call_id="tc_1", title="cellos-result-tools_cellos_submit_reply", status="completed", raw_output={}, session_update="tool_call_update")
    )

    result = collector.to_result()
    assert result.structured_result is not None
    assert result.structured_result.tool_name == "cellos-result-tools_cellos_submit_reply"


def test_collector_unwraps_mcp_result_wrapper():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.set_required_output_tool("cellos_submit_reply")
    collector.on_tool_start(
        ToolCallStart(tool_call_id="tc_1", title="cellos_submit_reply", raw_input={}, session_update="tool_call")
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1", title="cellos_submit_reply", status="completed", raw_output={"result": {"summary": "done"}}, session_update="tool_call_update"
        )
    )

    result = collector.to_result()
    assert result.structured_result.data["summary"] == "done"


def test_collector_captures_prefixed_tool_with_json_output():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.set_required_output_tool("cellos_submit_prompt")
    collector.on_tool_start(
        ToolCallStart(tool_call_id="tc_1", title="cellos-result-tools_cellos_submit_prompt", raw_input={}, session_update="tool_call")
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1", status="completed", raw_output={"output": '{"result":{"objective":"count","steps":["read"]}}', "metadata": {"truncated": False}}, session_update="tool_call_update"
        )
    )

    result = collector.to_result()
    assert result.structured_result.data == {"objective": "count", "steps": ["read"]}


# ── _payload_to_dict ───────────────────────────────────────────────


def test_payload_to_dict_direct():
    from cellos_acp.client import _EventCollector

    assert _EventCollector._payload_to_dict({"a": 1}) == {"a": 1}


def test_payload_to_dict_result_wrapper():
    from cellos_acp.client import _EventCollector

    assert _EventCollector._payload_to_dict({"result": {"x": 1}}) == {"x": 1}


def test_payload_to_dict_mcp_output_json_string():
    from cellos_acp.client import _EventCollector

    payload = {"output": '{"key": "val"}'}
    assert _EventCollector._payload_to_dict(payload) == {"key": "val"}


def test_payload_to_dict_mcp_output_result_wrapper():
    from cellos_acp.client import _EventCollector

    payload = {"output": '{"result":{"x": 1}}'}
    assert _EventCollector._payload_to_dict(payload) == {"x": 1}


def test_payload_to_dict_none_and_scalar():
    from cellos_acp.client import _EventCollector

    assert _EventCollector._payload_to_dict(None) == {}
    assert _EventCollector._payload_to_dict(42) == {"value": 42}


# ── on_event callback ──────────────────────────────────────────────


def test_on_event_callback_receives_events():
    from cellos_acp.client import _AcpClientImpl
    from acp.schema import AgentMessageChunk, TextContentBlock

    events = []

    async def on_event(event):
        events.append(event)

    impl = _AcpClientImpl(auto_approve=True)
    impl.set_on_event(on_event)
    impl.collector.session_id = "ses_cb"

    asyncio.run(impl.session_update("ses_cb", AgentMessageChunk(content=TextContentBlock(type="text", text="hello"), session_update="agent_message_chunk")))

    assert len(events) == 1
    assert events[0]["session_id"] == "ses_cb"


def test_on_event_callback_failure_does_not_crash():
    from cellos_acp.client import _AcpClientImpl
    from acp.schema import AgentMessageChunk, TextContentBlock

    events = []

    async def on_event(event):
        events.append(event)
        if len(events) == 1:
            raise RuntimeError("fail")

    impl = _AcpClientImpl(auto_approve=True)
    impl.set_on_event(on_event)
    impl.collector.session_id = "ses_cb"

    asyncio.run(impl.session_update("ses_cb", AgentMessageChunk(content=TextContentBlock(type="text", text="hello"), session_update="agent_message_chunk")))
    asyncio.run(impl.session_update("ses_cb", AgentMessageChunk(content=TextContentBlock(type="text", text="world"), session_update="agent_message_chunk")))

    assert len(events) == 2


# ── Permission handling ────────────────────────────────────────────


def test_auto_approve_selects_allow_option():
    from cellos_acp.client import _AcpClientImpl
    from acp.schema import PermissionOption, ToolCallUpdate

    impl = _AcpClientImpl(auto_approve=True)

    async def run():
        resp = await impl.request_permission(
            [PermissionOption(kind="allow_once", name="read", optionId="allow_read"), PermissionOption(kind="reject_once", name="deny", optionId="deny")],
            session_id="ses_1",
            tool_call=ToolCallUpdate(tool_call_id="tc_1", raw_input={}, session_update="tool_call"),
        )
        assert resp.outcome.outcome == "selected"
        assert resp.outcome.option_id == "allow_read"

    asyncio.run(run())


def test_auto_approve_cancels_when_no_allow_option():
    from cellos_acp.client import _AcpClientImpl
    from acp.schema import PermissionOption, ToolCallUpdate

    impl = _AcpClientImpl(auto_approve=True)

    async def run():
        resp = await impl.request_permission(
            [PermissionOption(kind="allow_once", name="read", optionId="read_file"), PermissionOption(kind="allow_once", name="write", optionId="write_file")],
            session_id="ses_1",
            tool_call=ToolCallUpdate(tool_call_id="tc_1", raw_input={}, session_update="tool_call"),
        )
        assert resp.outcome.outcome == "cancelled"

    asyncio.run(run())


def test_no_auto_approve_cancels():
    from cellos_acp.client import _AcpClientImpl
    from acp.schema import PermissionOption, ToolCallUpdate

    impl = _AcpClientImpl(auto_approve=False)

    async def run():
        resp = await impl.request_permission(
            [PermissionOption(kind="allow_once", name="read", optionId="allow_read")],
            session_id="ses_1",
            tool_call=ToolCallUpdate(tool_call_id="tc_1", raw_input={}, session_update="tool_call"),
        )
        assert resp.outcome.outcome == "cancelled"

    asyncio.run(run())


# ── CLI: _result_to_dict ───────────────────────────────────────────


def test_cli_json_includes_diagnostics():
    from cellos_acp.result import AcpRunResult
    from cellos_acp.__main__ import _result_to_dict

    d = _result_to_dict(
        AcpRunResult(text="hello", session_id="ses_1", message_id="msg_1", timeout=False)
    )
    assert "diagnostics" in d
    diag = d["diagnostics"]
    assert diag["session_id"] == "ses_1"
    assert diag["timeout"] is False


def test_cli_json_includes_structured_result():
    from cellos_acp.__main__ import _result_to_dict
    from cellos_acp.result import AcpRunResult, StructuredResult

    d = _result_to_dict(
        AcpRunResult(text="hello", structured_result=StructuredResult(kind="cellos_submit_reply", data={"success": True}, source="tool_call"))
    )
    assert d["structured_result"]["kind"] == "cellos_submit_reply"


# ── Model parameter ────────────────────────────────────────────────


def test_model_parameter_injects_opencode_config_env():
    from cellos_acp.client import AcpClient

    client = AcpClient(agent="opencode", model="lmstudio/test-model")
    assert "OPENCODE_CONFIG_CONTENT" in client._env
    assert json.loads(client._env["OPENCODE_CONFIG_CONTENT"])["model"] == "lmstudio/test-model"


# ── Schema helpers ─────────────────────────────────────────────────


def test_schema_helpers_cover_default_tool_names():
    from cellos_acp.schemas import make_blocker_schema, make_prompt_schema, make_reply_schema, schema_for_tool_name

    assert make_prompt_schema()["name"] == "cellos_submit_prompt"
    assert make_reply_schema()["name"] == "cellos_submit_reply"
    assert make_blocker_schema()["name"] == "cellos_report_blocker"


def test_schema_for_unknown_tool_returns_fallback():
    from cellos_acp.schemas import schema_for_tool_name

    schema = schema_for_tool_name("my_custom_tool")
    assert schema["name"] == "my_custom_tool"
    assert "parameters" in schema


# ── MCP server spawn + cleanup ─────────────────────────────────────


def test_spawn_mcp_server_returns_live_process():
    from cellos_acp.mcp_tools import spawn_mcp_server
    from cellos_acp.schemas import make_reply_schema

    proc = spawn_mcp_server([make_reply_schema()])
    try:
        assert proc.proc.poll() is None
        assert proc.mcp_server.name == "cellos-result-tools"
    finally:
        proc.proc.terminate()
        proc.proc.wait(timeout=5)


def test_run_with_output_tools_passes_mcp_servers_and_cleans_up():
    from cellos_acp.client import AcpClient
    from cellos_acp.schemas import make_reply_schema
    import cellos_acp.client as client_module

    class FakeProc:
        def __init__(self):
            self.terminated = False
            self.waited = False

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waited = True

        def kill(self):
            pass

    fake_conn = SimpleNamespace(new_session_kwargs=None)

    async def _fake_init(**_): ...

    async def _fake_new_session(**kw):
        fake_conn.new_session_kwargs = kw
        return SimpleNamespace(session_id="ses_fake")

    async def _fake_prompt(**_):
        return SimpleNamespace(stop_reason="end_turn")

    class FakeCtx:
        def __init__(self):
            self.conn = SimpleNamespace(initialize=_fake_init, new_session=_fake_new_session, prompt=_fake_prompt)

        async def __aenter__(self):
            return self.conn, object()

        async def __aexit__(self, *a): ...

    fake_mcp = SimpleNamespace(proc=FakeProc(), mcp_server=object())
    client = AcpClient(agent="opencode", timeout=5, text_wait=0)

    orig_spawn_agent = client_module.spawn_agent_process
    orig_spawn_mcp = client_module.spawn_mcp_server
    try:
        client_module.spawn_agent_process = lambda *a, **kw: FakeCtx()
        client_module.spawn_mcp_server = lambda _: fake_mcp
        result = asyncio.run(client.run("hello", output_tools=[make_reply_schema()], required_output_tool="cellos_submit_reply"))
    finally:
        client_module.spawn_agent_process = orig_spawn_agent
        client_module.spawn_mcp_server = orig_spawn_mcp

    assert result.success is True
    assert fake_conn.new_session_kwargs["mcp_servers"] == [fake_mcp.mcp_server]
    assert fake_mcp.proc.terminated is True
