"""Unified result type for ACP agent execution."""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class StructuredResult:
    """Structured result captured from a tool call."""

    kind: str
    data: dict[str, Any]
    source: str
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclasses.dataclass
class ToolCallRecord:
    """Record of a single tool call."""

    tool_call_id: str
    title: str
    status: str = ""
    raw_input: dict = dataclasses.field(default_factory=dict)
    raw_output: Any = None
    started_at: str | None = None
    updated_at: str | None = None
    nested_session_id: str | None = None


@dataclasses.dataclass
class AcpRunResult:
    """Unified result from an ACP agent execution.

    Attributes:
        text: Concatenated text from AgentMessageChunk events.
        thinking: Concatenated text from AgentThoughtChunk events.
        tool_calls: List of tool call records.
        active_tool_calls: Tool calls that have not reached terminal status.
        stop_reason: Final stop reason (e.g. "end_turn").
        error: Exception if execution failed, else None.
        session_id: ACP session identifier.
        message_id: ACP message identifier.
        started_at: ISO-8601 timestamp when execution started.
        completed_at: ISO-8601 timestamp when execution completed.
        last_event_at: ISO-8601 timestamp of last received event.
        last_event_type: Type name of last received event.
        last_message_preview: Bounded preview of last message chunk.
        last_thought_preview: Bounded preview of last thought chunk.
        timeout: Whether execution timed out.
        aborted: Whether execution was aborted.
        error_type: Type name of the error.
        error_message: Human-readable error message.
    """

    text: str = ""
    thinking: str = ""
    tool_calls: list[ToolCallRecord] = dataclasses.field(default_factory=list)
    active_tool_calls: list[ToolCallRecord] = dataclasses.field(default_factory=list)
    structured_result: StructuredResult | None = None
    stop_reason: str = ""
    error: Exception | None = None

    session_id: str | None = None
    message_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    last_event_at: str | None = None
    last_event_type: str | None = None
    last_message_preview: str | None = None
    last_thought_preview: str | None = None
    timeout: bool = False
    aborted: bool = False
    error_type: str | None = None
    error_message: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def combined_text(self) -> str:
        """Primary text output — prefers text, falls back to thinking."""
        return self.text or self.thinking
