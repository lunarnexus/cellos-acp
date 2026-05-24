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


def test_event_collector_thought_only_promotes():
    from cellos_acp.client import _EventCollector
    from acp.schema import AgentThoughtChunk, TextContentBlock

    collector = _EventCollector(thought_only=True)
    chunk = AgentThoughtChunk(
        content=TextContentBlock(type="text", text="thought text"),
        session_update="agent_thought_chunk",
    )
    collector.on_thought_chunk(chunk)
    result = collector.to_result()
    assert result.text == "thought text"
    assert result.thinking == ""


def test_event_collector_normal_mode():
    from cellos_acp.client import _EventCollector
    from acp.schema import AgentMessageChunk, AgentThoughtChunk, TextContentBlock

    collector = _EventCollector(thought_only=False)
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
