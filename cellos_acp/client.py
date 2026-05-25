"""Core ACP client wrapping agent-client-protocol SDK."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
from acp.client.connection import ClientSideConnection
from acp.interfaces import Client
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AllowedOutcome,
    ClientCapabilities,
    Implementation,
    PermissionOption,
    RequestPermissionResponse,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
)

from .result import AcpRunResult, ToolCallRecord

logger = logging.getLogger(__name__)


class _EventCollector:
    """Collects ACP events into an AcpRunResult."""

    def __init__(self, thought_only: bool = False):
        self.thought_only = thought_only
        self.text_parts: list[str] = []
        self.thinking_parts: list[str] = []
        self.tool_calls: dict[str, ToolCallRecord] = {}
        self.stop_reason: str = ""

    def on_message_chunk(self, chunk: AgentMessageChunk) -> None:
        content = getattr(chunk, "content", None)
        if content and hasattr(content, "text"):
            text = content.text
            if text:
                self.text_parts.append(text)

    def on_thought_chunk(self, chunk: AgentThoughtChunk) -> None:
        content = getattr(chunk, "content", None)
        if content and hasattr(content, "text"):
            self.thinking_parts.append(content.text)

    def on_tool_start(self, update: ToolCallStart) -> None:
        self.tool_calls[update.tool_call_id] = ToolCallRecord(
            tool_call_id=update.tool_call_id,
            title=update.title or "",
            raw_input=update.raw_input or {},
        )

    def on_tool_progress(self, update: ToolCallProgress) -> None:
        rec = self.tool_calls.get(update.tool_call_id)
        if rec:
            rec.status = update.status or ""
            rec.raw_output = update.raw_output

    def to_result(self) -> AcpRunResult:
        text = "".join(self.text_parts)
        thinking = "".join(self.thinking_parts)

        # For thought-only adapters (opencode), promote thinking → text
        if self.thought_only and not text and thinking:
            text = thinking
            thinking = ""

        return AcpRunResult(
            text=text,
            thinking=thinking,
            tool_calls=list(self.tool_calls.values()),
            stop_reason=self.stop_reason,
        )


class _AcpClientImpl(Client):
    """ACP Client interface implementation backed by an EventCollector."""

    def __init__(self, thought_only: bool = False, auto_approve: bool = True):
        self.collector = _EventCollector(thought_only=thought_only)
        self.auto_approve = auto_approve

    async def session_update(
        self, session_id: str, update: Any, **kwargs: Any
    ) -> None:
        if isinstance(update, AgentMessageChunk):
            self.collector.on_message_chunk(update)
        elif isinstance(update, AgentThoughtChunk):
            self.collector.on_thought_chunk(update)
        elif isinstance(update, ToolCallStart):
            self.collector.on_tool_start(update)
        elif isinstance(update, ToolCallProgress):
            self.collector.on_tool_progress(update)

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        if self.auto_approve:
            # Default: allow the first "allow" option, or the first option
            allow_id = "allow"
            for opt in options:
                if "allow" in opt.option_id.lower():
                    allow_id = opt.option_id
                    break
            return RequestPermissionResponse(
                outcome=AllowedOutcome(outcome="selected", option_id=allow_id)
            )
        # If not auto-approve, deny by default
        return RequestPermissionResponse(
            outcome=AllowedOutcome(outcome="cancelled")
        )


class AcpClient:
    """Lightweight ACP client for CelloS.

    Spawns an agent as a subprocess, sends a prompt, collects events,
    and returns an AcpRunResult.

    Example:
        >>> import asyncio
        >>> async def main():
        ...     client = AcpClient(agent="opencode", cwd="/tmp")
        ...     result = await client.run("explain this code")
        ...     print(result.combined_text)
        >>> asyncio.run(main())
    """

    def __init__(
        self,
        agent: str = "opencode",
        command: str | None = None,
        args: list[str] | None = None,
        cwd: str = ".",
        env: dict[str, str] | None = None,
        thought_only: bool | None = None,
        auto_approve: bool = True,
        timeout: float | None = None,
        quiet_wait: float = 1.0,
    ):
        """
        Args:
            agent: Name of registered adapter (e.g. "opencode").
            command: Override command (ignores adapter).
            args: Override args (ignores adapter).
            cwd: Working directory for the agent.
            env: Extra environment variables.
            thought_only: Force thought-only mode. Auto-detected from adapter quirks.
            auto_approve: Auto-approve all permission requests.
            timeout: Total timeout in seconds for the entire lifecycle.
            quiet_wait: Seconds to wait after response for late streaming chunks.
                Set to 0 to disable. Default 1.0 for agents that send chunks after result.
        """
        from .registry import get_adapter

        if command is not None:
            self._command = command
            self._args = args or []
            if thought_only is None:
                thought_only = False
        else:
            adapter = get_adapter(agent)
            self._command = adapter.command
            self._args = adapter.args
            if thought_only is None:
                thought_only = adapter.quirks.get("thought_only", False)

        self._cwd = cwd
        self._env = env
        self._thought_only = thought_only
        self._auto_approve = auto_approve
        self._timeout = timeout
        self._quiet_wait = quiet_wait

    async def run(self, prompt: str) -> AcpRunResult:
        """Execute a prompt against the agent and return the result.

        After the prompt response arrives, waits `quiet_wait` seconds
        to catch late streaming chunks (opencode sends chunks after result).
        """

        impl = _AcpClientImpl(
            thought_only=self._thought_only,
            auto_approve=self._auto_approve,
        )

        async def _execute() -> AcpRunResult:
            env = dict(self._env) if self._env else None

            async with spawn_agent_process(
                impl, self._command, *self._args, env=env, cwd=self._cwd
            ) as (conn, proc):
                # Initialize
                await conn.initialize(
                    protocol_version=PROTOCOL_VERSION,
                    client_info=Implementation(
                        name="cellos-acp", version="0.1.0"
                    ),
                    client_capabilities=ClientCapabilities(),
                )

                # Create session
                session = await conn.new_session(cwd=self._cwd)

                # Send prompt
                response = await conn.prompt(
                    session_id=session.session_id,
                    prompt=[text_block(prompt)],
                    message_id=str(uuid4()),
                )

                # Extract stop reason
                if response:
                    impl.collector.stop_reason = getattr(
                        response, "stop_reason", ""
                    ) or ""

                # Wait for late events (opencode sends chunks after result)
                # Only wait if quiet_wait > 0
                if self._quiet_wait > 0:
                    await asyncio.sleep(self._quiet_wait)

                return impl.collector.to_result()

        if self._timeout:
            try:
                return await asyncio.wait_for(_execute(), timeout=self._timeout)
            except asyncio.TimeoutError:
                return AcpRunResult(error=TimeoutError(f"ACP timeout after {self._timeout}s"))
        else:
            try:
                return await _execute()
            except Exception as e:
                return AcpRunResult(error=e)
