"""Unified result type for ACP agent execution."""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class ToolCallRecord:
    """Record of a single tool call."""

    tool_call_id: str
    title: str
    status: str = ""
    raw_input: dict = dataclasses.field(default_factory=dict)
    raw_output: Any = None


@dataclasses.dataclass
class AcpRunResult:
    """Unified result from an ACP agent execution.

    Attributes:
        text: Concatenated text from AgentMessageChunk events.
        thinking: Concatenated text from AgentThoughtChunk events.
        tool_calls: List of tool call records.
        stop_reason: Final stop reason (e.g. "end_turn").
        error: Exception if execution failed, else None.
    """

    text: str = ""
    thinking: str = ""
    tool_calls: list[ToolCallRecord] = dataclasses.field(default_factory=list)
    stop_reason: str = ""
    error: Exception | None = None

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def combined_text(self) -> str:
        """Primary text output — prefers text, falls back to thinking."""
        return self.text or self.thinking
