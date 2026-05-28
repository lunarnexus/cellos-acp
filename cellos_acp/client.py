"""Core ACP client wrapping agent-client-protocol SDK."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
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

_DEBUG_TRUNCATE = 500


def _debug_truncate(value: Any, limit: int = _DEBUG_TRUNCATE) -> str:
    """Truncate a value for debug logging, appending [TRUNCATED] marker."""
    s = json.dumps(value, default=str) if not isinstance(value, str) else value
    if len(s) <= limit:
        return s
    return f"{s[:limit]}... [TRUNCATED: {len(s)} chars total]"


class _EventCollector:
    """Collects ACP events into an AcpRunResult."""

    def __init__(self):
        self.text_parts: list[str] = []
        self.thinking_parts: list[str] = []
        self.tool_calls: dict[str, ToolCallRecord] = {}
        self.stop_reason: str = ""

    def on_message_chunk(self, chunk: AgentMessageChunk) -> None:
        content = getattr(chunk, "content", None)
        if content and hasattr(content, "text"):
            text = content.text
            if text:
                logger.debug("message_chunk: %s", _debug_truncate(text))
                self.text_parts.append(text)

    def on_thought_chunk(self, chunk: AgentThoughtChunk) -> None:
        content = getattr(chunk, "content", None)
        if content and hasattr(content, "text"):
            logger.debug("thought_chunk: %s", _debug_truncate(content.text))
            self.thinking_parts.append(content.text)

    def on_tool_start(self, update: ToolCallStart) -> None:
        logger.debug(
            "tool_start id=%s title=%s input=%s",
            update.tool_call_id,
            update.title or "",
            _debug_truncate(update.raw_input or {}),
        )
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
            logger.debug(
                "tool_progress id=%s status=%s output=%s",
                update.tool_call_id,
                update.status or "",
                _debug_truncate(update.raw_output),
            )

    def to_result(self) -> AcpRunResult:
        text = "".join(self.text_parts)
        thinking = "".join(self.thinking_parts)

        logger.debug(
            "to_result text=%d thinking=%d tools=%d stop=%s",
            len(text),
            len(thinking),
            len(self.tool_calls),
            self.stop_reason,
        )

        return AcpRunResult(
            text=text,
            thinking=thinking,
            tool_calls=list(self.tool_calls.values()),
            stop_reason=self.stop_reason,
        )


class _AcpClientImpl(Client):
    """ACP Client interface implementation backed by an EventCollector."""

    def __init__(self, auto_approve: bool = True):
        self.collector = _EventCollector()
        self.auto_approve = auto_approve

    async def session_update(
        self, session_id: str, update: Any, **kwargs: Any
    ) -> None:
        update_type = type(update).__name__
        logger.debug("session_update session=%s type=%s", session_id, update_type)
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
        option_ids = [opt.option_id for opt in options]
        logger.debug(
            "request_permission session=%s options=%s auto_approve=%s",
            session_id,
            option_ids,
            self.auto_approve,
        )
        if self.auto_approve:
            # Only auto-approve if an explicit "allow" option exists.
            allow_id = ""
            for opt in options:
                if "allow" in opt.option_id.lower():
                    allow_id = opt.option_id
                    break
            if not allow_id:
                logger.warning(
                    "No 'allow' option found in permission request; cancelling."
                )
                return RequestPermissionResponse(
                    outcome=AllowedOutcome(outcome="cancelled")
                )
            logger.debug("permission auto-approved: option=%s", allow_id)
            return RequestPermissionResponse(
                outcome=AllowedOutcome(outcome="selected", option_id=allow_id)
            )
        logger.debug("permission denied (auto_approve=False)")
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
        auto_approve: bool = True,
        timeout: float | None = 300,
        text_wait: float = 1.0,
    ):
        """
        Args:
            agent: Name of registered adapter (e.g. "opencode").
            command: Override command (ignores adapter).
            args: Override args (ignores adapter).
            cwd: Working directory for the agent.
            env: Extra environment variables.
            auto_approve: Auto-approve all permission requests.
            timeout: Total timeout in seconds for the entire lifecycle.
            text_wait: Seconds to wait after response for late streaming chunks.
                Set to 0 to disable. Default 1.0 for agents that send chunks after result.
        """
        from .registry import get_adapter

        if command is not None:
            self._command = command
            self._args = args or []
            adapter_env = {}
        else:
            adapter = get_adapter(agent)
            self._command = adapter.command
            self._args = adapter.args
            adapter_env = adapter.env or {}

        self._cwd = cwd
        self._env = {**adapter_env, **(env or {})}
        self._auto_approve = auto_approve
        self._timeout = timeout
        self._text_wait = text_wait

        logger.debug(
            "AcpClient init command=%s args=%s cwd=%s timeout=%s text_wait=%s auto_approve=%s",
            self._command,
            self._args,
            self._cwd,
            self._timeout,
            self._text_wait,
            self._auto_approve,
        )

    async def run(self, prompt: str) -> AcpRunResult:
        """Execute a prompt against the agent and return the result.

        After the prompt response arrives, waits `text_wait` seconds
        to catch late streaming chunks (opencode sends chunks after result).
        """

        impl = _AcpClientImpl(
            auto_approve=self._auto_approve,
        )

        async def _execute() -> AcpRunResult:
            env = dict(self._env) if self._env else None
            cmd_line = [self._command, *self._args]

            logger.debug("spawning %s cwd=%s env=%s", cmd_line, self._cwd, env)

            async with spawn_agent_process(
                impl, self._command, *self._args, env=env, cwd=self._cwd
            ) as (conn, proc):
                # Initialize
                logger.debug("initializing protocol=%s", PROTOCOL_VERSION)
                await conn.initialize(
                    protocol_version=PROTOCOL_VERSION,
                    client_info=Implementation(
                        name="cellos-acp", version="0.1.0"
                    ),
                    client_capabilities=ClientCapabilities(),
                )

                # Create session
                session = await conn.new_session(cwd=self._cwd)
                logger.debug("session created id=%s", session.session_id)

                # Send prompt
                msg_id = str(uuid4())
                logger.debug(
                    "sending prompt len=%s id=%s", len(prompt), msg_id
                )
                response = await conn.prompt(
                    session_id=session.session_id,
                    prompt=[text_block(prompt)],
                    message_id=msg_id,
                )

                # Extract stop reason
                if response:
                    impl.collector.stop_reason = getattr(
                        response, "stop_reason", ""
                    ) or ""
                    logger.debug(
                        "response received stop_reason=%s",
                        impl.collector.stop_reason,
                    )

                # Wait for late events (opencode sends chunks after result)
                # Only wait if text_wait > 0
                if self._text_wait > 0:
                    logger.debug("waiting %.1fs for late chunks", self._text_wait)
                    await asyncio.sleep(self._text_wait)

                return impl.collector.to_result()

        if self._timeout:
            try:
                return await asyncio.wait_for(_execute(), timeout=self._timeout)
            except asyncio.TimeoutError:
                logger.error(
                    "ACP timeout after %.1fs", self._timeout, exc_info=True
                )
                return AcpRunResult(
                    error=TimeoutError(f"ACP timeout after {self._timeout}s")
                )
            except Exception as e:
                logger.error("execution error: %s", e, exc_info=True)
                return AcpRunResult(error=e)
        try:
            return await _execute()
        except Exception as e:
            logger.error("execution error: %s", e, exc_info=True)
            return AcpRunResult(error=e)
