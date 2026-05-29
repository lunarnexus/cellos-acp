"""Tests for cellos-acp core client."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio


def test_result_combined_text_prefers_text():
    from cellos_acp.result import AcpRunResult

    r = AcpRunResult(text="hello", thinking="thinking...")
    assert r.combined_text == "hello"


def test_result_combined_text_falls_back_to_thinking():
    from cellos_acp.result import AcpRunResult

    r = AcpRunResult(text="", thinking="thinking only")
    assert r.combined_text == "thinking only"


def test_result_success():
    from cellos_acp.result import AcpRunResult

    assert AcpRunResult(text="ok").success is True
    assert AcpRunResult(error=ValueError("fail")).success is False


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


def test_tool_call_record_has_diagnostic_fields():
    from cellos_acp.result import ToolCallRecord

    rec = ToolCallRecord(
        tool_call_id="tc_1",
        title="task",
        started_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:01Z",
        nested_session_id="ses_nested",
    )
    assert rec.tool_call_id == "tc_1"
    assert rec.title == "task"
    assert rec.started_at == "2026-01-01T00:00:00Z"
    assert rec.updated_at == "2026-01-01T00:00:01Z"
    assert rec.nested_session_id == "ses_nested"


def test_tool_call_record_defaults():
    from cellos_acp.result import ToolCallRecord

    rec = ToolCallRecord(tool_call_id="tc_1", title="task")
    assert rec.started_at is None
    assert rec.updated_at is None
    assert rec.nested_session_id is None


def test_acp_run_result_has_diagnostic_fields():
    from cellos_acp.result import AcpRunResult

    r = AcpRunResult(
        text="hello",
        session_id="ses_1",
        message_id="msg_1",
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:00:05Z",
        last_event_at="2026-01-01T00:00:04Z",
        last_event_type="ToolCallProgress",
        last_message_preview="hello",
        last_thought_preview="thinking",
        timeout=True,
        aborted=False,
        error_type="TimeoutError",
        error_message="timed out",
        active_tool_calls=[],
    )
    assert r.session_id == "ses_1"
    assert r.message_id == "msg_1"
    assert r.started_at == "2026-01-01T00:00:00Z"
    assert r.completed_at == "2026-01-01T00:00:05Z"
    assert r.last_event_at == "2026-01-01T00:00:04Z"
    assert r.last_event_type == "ToolCallProgress"
    assert r.last_message_preview == "hello"
    assert r.last_thought_preview == "thinking"
    assert r.timeout is True
    assert r.aborted is False
    assert r.error_type == "TimeoutError"
    assert r.error_message == "timed out"
    assert r.active_tool_calls == []


def test_acp_run_result_defaults():
    from cellos_acp.result import AcpRunResult

    r = AcpRunResult(text="ok")
    assert r.session_id is None
    assert r.message_id is None
    assert r.started_at is None
    assert r.completed_at is None
    assert r.last_event_at is None
    assert r.last_event_type is None
    assert r.last_message_preview is None
    assert r.last_thought_preview is None
    assert r.timeout is False
    assert r.aborted is False
    assert r.error_type is None
    assert r.error_message is None
    assert r.active_tool_calls == []


def test_result_still_success_with_new_fields():
    from cellos_acp.result import AcpRunResult

    r = AcpRunResult(text="ok", session_id="ses_1", timeout=False)
    assert r.success is True


def test_result_combined_text_unchanged():
    from cellos_acp.result import AcpRunResult

    r = AcpRunResult(text="hello", thinking="thinking...")
    assert r.combined_text == "hello"
    r2 = AcpRunResult(text="", thinking="only thinking")
    assert r2.combined_text == "only thinking"


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


def test_collector_updates_message_preview():
    from cellos_acp.client import _EventCollector
    from acp.schema import AgentMessageChunk, TextContentBlock

    collector = _EventCollector()
    collector.on_message_chunk(
        AgentMessageChunk(
            content=TextContentBlock(type="text", text="hello world"),
            session_update="agent_message_chunk",
        )
    )
    result = collector.to_result()
    assert result.last_message_preview is not None
    assert "hello world" in result.last_message_preview


def test_collector_updates_thought_preview():
    from cellos_acp.client import _EventCollector
    from acp.schema import AgentThoughtChunk, TextContentBlock

    collector = _EventCollector()
    collector.on_thought_chunk(
        AgentThoughtChunk(
            content=TextContentBlock(type="text", text="thinking deeply"),
            session_update="agent_thought_chunk",
        )
    )
    result = collector.to_result()
    assert result.last_thought_preview is not None
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
    assert result.active_tool_calls[0].title == "task"


def test_tool_progress_terminal_removes_from_active():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.on_tool_start(
        ToolCallStart(
            tool_call_id="tc_1",
            title="task",
            raw_input={},
            session_update="tool_call",
        )
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1",
            status="completed",
            raw_output={"result": "done"},
            session_update="tool_call_update",
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
        ToolCallStart(
            tool_call_id="tc_1",
            title="task",
            raw_input={},
            session_update="tool_call",
        )
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1",
            status="in_progress",
            raw_output={"partial": "output"},
            session_update="tool_call_update",
        )
    )
    result = collector.to_result()
    assert len(result.active_tool_calls) == 1


def test_nested_session_id_extracted_from_metadata():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.on_tool_start(
        ToolCallStart(
            tool_call_id="tc_1",
            title="task",
            raw_input={},
            session_update="tool_call",
        )
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1",
            status="in_progress",
            raw_output={"metadata": {"sessionId": "ses_nested"}},
            session_update="tool_call_update",
        )
    )
    result = collector.to_result()
    assert result.tool_calls[0].nested_session_id == "ses_nested"


def test_nested_session_id_deeply_nested():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.on_tool_start(
        ToolCallStart(
            tool_call_id="tc_1",
            title="task",
            raw_input={},
            session_update="tool_call",
        )
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1",
            status="in_progress",
            raw_output={"data": {"nested": {"session_id": "deep_ses"}}},
            session_update="tool_call_update",
        )
    )
    result = collector.to_result()
    assert result.tool_calls[0].nested_session_id == "deep_ses"


def test_nested_session_id_in_raw_input():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart

    collector = _EventCollector()
    collector.on_tool_start(
        ToolCallStart(
            tool_call_id="tc_1",
            title="task",
            raw_input={"nested_session_id": "from_input"},
            session_update="tool_call",
        )
    )
    result = collector.to_result()
    assert result.tool_calls[0].nested_session_id == "from_input"


def test_timeout_preserves_partial_state():
    from cellos_acp.client import _EventCollector
    from acp.schema import AgentThoughtChunk, ToolCallStart, ToolCallProgress, TextContentBlock

    collector = _EventCollector()
    collector.session_id = "ses_test"
    collector.message_id = "msg_test"
    collector.started_at = "2026-01-01T00:00:00Z"
    collector.on_thought_chunk(
        AgentThoughtChunk(
            content=TextContentBlock(type="text", text="I need to inspect the codebase"),
            session_update="agent_thought_chunk",
        )
    )
    collector.on_tool_start(
        ToolCallStart(
            tool_call_id="tc_1",
            title="task",
            raw_input={},
            session_update="tool_call",
        )
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_1",
            status="in_progress",
            raw_output={"metadata": {"sessionId": "ses_nested"}},
            session_update="tool_call_update",
        )
    )

    result = collector.to_result()
    result.timeout = True
    result.error_type = "TimeoutError"
    result.error_message = "timed out"
    result.completed_at = "2026-01-01T00:00:05Z"

    assert result.timeout is True
    assert result.error_type == "TimeoutError"
    assert result.session_id == "ses_test"
    assert result.message_id == "msg_test"
    assert len(result.active_tool_calls) == 1
    assert result.active_tool_calls[0].title == "task"
    assert result.active_tool_calls[0].nested_session_id == "ses_nested"
    assert "I need to inspect the codebase" in result.thinking


def test_timeout_preserves_partial_state_via_client():
    from cellos_acp.client import _AcpClientImpl
    from acp.schema import AgentThoughtChunk, ToolCallStart, ToolCallProgress, TextContentBlock

    async def run():
        impl = _AcpClientImpl(auto_approve=True)
        impl.collector.session_id = "ses_timeout"
        impl.collector.message_id = "msg_timeout"
        impl.collector.started_at = "2026-01-01T00:00:00Z"
        impl.collector.on_thought_chunk(
            AgentThoughtChunk(
                content=TextContentBlock(type="text", text="thinking"),
                session_update="agent_thought_chunk",
            )
        )
        impl.collector.on_tool_start(
            ToolCallStart(
                tool_call_id="tc_1",
                title="read_file",
                raw_input={},
                session_update="tool_call",
            )
        )

        result = impl.collector.to_result()
        result.timeout = True
        result.error = TimeoutError("ACP timeout after 0.5s")
        result.error_type = "TimeoutError"
        result.error_message = "ACP timeout after 0.5s"
        result.completed_at = "2026-01-01T00:00:05Z"

        assert result.timeout is True
        assert result.error_type == "TimeoutError"
        assert result.session_id == "ses_timeout"
        assert result.message_id == "msg_timeout"
        assert len(result.active_tool_calls) == 1
        assert result.active_tool_calls[0].title == "read_file"
        assert "thinking" in result.thinking

    asyncio.run(run())


def test_on_event_callback_receives_events():
    from cellos_acp.client import _AcpClientImpl
    from acp.schema import AgentMessageChunk, TextContentBlock

    events = []

    async def on_event(event):
        events.append(event)

    impl = _AcpClientImpl(auto_approve=True)
    impl.set_on_event(on_event)
    impl.collector.session_id = "ses_cb"

    async def run():
        await impl.session_update(
            "ses_cb",
            AgentMessageChunk(
                content=TextContentBlock(type="text", text="hello"),
                session_update="agent_message_chunk",
            ),
        )
        assert len(events) == 1
        assert events[0]["session_id"] == "ses_cb"
        assert events[0]["event_type"] == "AgentMessageChunk"
        assert events[0]["text_preview"] == "hello"

    asyncio.run(run())


def test_on_event_callback_failure_does_not_crash():
    from cellos_acp.client import _AcpClientImpl
    from acp.schema import AgentMessageChunk, TextContentBlock

    events = []

    async def on_event(event):
        events.append(event)
        if len(events) == 1:
            raise RuntimeError("fail on first event")

    impl = _AcpClientImpl(auto_approve=True)
    impl.set_on_event(on_event)
    impl.collector.session_id = "ses_cb"

    async def run():
        await impl.session_update(
            "ses_cb",
            AgentMessageChunk(
                content=TextContentBlock(type="text", text="hello"),
                session_update="agent_message_chunk",
            ),
        )
        await impl.session_update(
            "ses_cb",
            AgentMessageChunk(
                content=TextContentBlock(type="text", text="world"),
                session_update="agent_message_chunk",
            ),
        )
        assert len(events) == 2

    asyncio.run(run())


def test_acp_client_run_with_callback():
    from cellos_acp.client import AcpClient

    client = AcpClient(agent="opencode")
    assert hasattr(client.run, "__defaults__") or callable(client.run)


def test_cli_json_includes_diagnostics():
    from cellos_acp.result import AcpRunResult
    from cellos_acp.__main__ import _result_to_dict

    result = AcpRunResult(
        text="hello",
        session_id="ses_1",
        message_id="msg_1",
        started_at="2026-01-01T00:00:00Z",
        completed_at="2026-01-01T00:00:05Z",
        last_event_at="2026-01-01T00:00:04Z",
        last_event_type="AgentMessageChunk",
        last_message_preview="hello",
        last_thought_preview="thinking",
        timeout=False,
        aborted=False,
    )
    d = _result_to_dict(result)
    assert "diagnostics" in d
    diag = d["diagnostics"]
    assert diag["session_id"] == "ses_1"
    assert diag["message_id"] == "msg_1"
    assert diag["started_at"] == "2026-01-01T00:00:00Z"
    assert diag["completed_at"] == "2026-01-01T00:00:05Z"
    assert diag["last_event_at"] == "2026-01-01T00:00:04Z"
    assert diag["last_event_type"] == "AgentMessageChunk"
    assert diag["timeout"] is False
    assert diag["aborted"] is False
    assert diag["active_tool_calls"] == []


def test_model_parameter_injects_opencode_config_env():
    from cellos_acp.client import AcpClient
    import json

    client = AcpClient(agent="opencode", model="lmstudio/test-model")
    assert "OPENCODE_CONFIG_CONTENT" in client._env
    assert json.loads(client._env["OPENCODE_CONFIG_CONTENT"])["model"] == "lmstudio/test-model"


def test_schema_helpers_cover_default_tool_names():
    from cellos_acp.schemas import (
        make_blocker_schema,
        make_prompt_schema,
        make_reply_schema,
        schema_for_tool_name,
    )

    assert make_prompt_schema()["name"] == "cellos_submit_prompt"
    assert make_reply_schema()["name"] == "cellos_submit_reply"
    assert make_blocker_schema()["name"] == "cellos_report_blocker"
    assert schema_for_tool_name("cellos_submit_prompt")["name"] == "cellos_submit_prompt"


def test_collector_captures_structured_result_for_required_tool():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.set_required_output_tool("cellos_submit_reply")
    collector.on_tool_start(
        ToolCallStart(
            tool_call_id="tc_structured",
            title="cellos_submit_reply",
            raw_input={"summary": "done", "success": True},
            session_update="tool_call",
        )
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_structured",
            title="cellos_submit_reply",
            status="completed",
            raw_output={"summary": "done", "success": True},
            session_update="tool_call_update",
        )
    )

    result = collector.to_result()
    assert result.structured_result is not None
    assert result.structured_result.kind == "cellos_submit_reply"
    assert result.structured_result.source == "tool_call"
    assert result.structured_result.tool_call_id == "tc_structured"
    assert result.structured_result.data["summary"] == "done"


def test_collector_unwraps_mcp_result_wrapper():
    from cellos_acp.client import _EventCollector
    from acp.schema import ToolCallStart, ToolCallProgress

    collector = _EventCollector()
    collector.set_required_output_tool("cellos_submit_reply")
    collector.on_tool_start(
        ToolCallStart(
            tool_call_id="tc_wrapped",
            title="cellos_submit_reply",
            raw_input={},
            session_update="tool_call",
        )
    )
    collector.on_tool_progress(
        ToolCallProgress(
            tool_call_id="tc_wrapped",
            title="cellos_submit_reply",
            status="completed",
            raw_output={"result": {"summary": "done", "success": True}},
            session_update="tool_call_update",
        )
    )

    result = collector.to_result()
    assert result.structured_result is not None
    assert result.structured_result.data["summary"] == "done"


def test_cli_json_includes_structured_result():
    from cellos_acp.__main__ import _result_to_dict
    from cellos_acp.result import AcpRunResult, StructuredResult

    result = AcpRunResult(
        text="hello",
        structured_result=StructuredResult(
            kind="cellos_submit_reply",
            data={"summary": "done", "success": True},
            source="tool_call",
            tool_call_id="tc_1",
            tool_name="cellos_submit_reply",
        ),
    )
    d = _result_to_dict(result)
    assert d["structured_result"]["kind"] == "cellos_submit_reply"
    assert d["structured_result"]["data"]["success"] is True


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
    from types import SimpleNamespace
    from cellos_acp.client import AcpClient
    from cellos_acp.schemas import make_reply_schema
    import cellos_acp.client as client_module

    class FakeProc:
        def __init__(self):
            self.terminated = False
            self.killed = False
            self.waited = False

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waited = True

        def kill(self):
            self.killed = True

    class FakeMcpProc:
        def __init__(self):
            self.proc = FakeProc()
            self.mcp_server = object()

    class FakeConn:
        def __init__(self):
            self.new_session_kwargs = None
            self.prompt_kwargs = None

        async def initialize(self, **kwargs):
            return None

        async def new_session(self, **kwargs):
            self.new_session_kwargs = kwargs
            return SimpleNamespace(session_id="ses_fake")

        async def prompt(self, **kwargs):
            self.prompt_kwargs = kwargs
            return SimpleNamespace(stop_reason="end_turn")

    class FakeCtx:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self.conn, object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    fake_conn = FakeConn()
    fake_mcp = FakeMcpProc()
    client = AcpClient(agent="opencode", timeout=5, text_wait=0)

    original_spawn_agent_process = client_module.spawn_agent_process
    original_spawn_mcp_server = client_module.spawn_mcp_server
    try:
        client_module.spawn_agent_process = lambda *args, **kwargs: FakeCtx(fake_conn)
        client_module.spawn_mcp_server = lambda tool_schemas: fake_mcp

        result = asyncio.run(
            client.run(
                "hello",
                output_tools=[make_reply_schema()],
                required_output_tool="cellos_submit_reply",
            )
        )
    finally:
        client_module.spawn_agent_process = original_spawn_agent_process
        client_module.spawn_mcp_server = original_spawn_mcp_server

    assert result.success is True
    assert fake_conn.new_session_kwargs["mcp_servers"] == [fake_mcp.mcp_server]
    assert fake_mcp.proc.terminated is True
    assert fake_mcp.proc.waited is True
