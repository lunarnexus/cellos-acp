"""Core ACP client wrapping agent-client-protocol SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import subprocess
from typing import Any
from uuid import uuid4

from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
from acp.interfaces import Client
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AllowedOutcome,
    DeniedOutcome,
    ClientCapabilities,
    Implementation,
    PermissionOption,
    RequestPermissionResponse,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
)

from .mcp_tools import CELLOS_MCP_SERVER, spawn_mcp_server
from .result import AcpRunResult, StructuredResult, ToolCallRecord

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

    PREVIEW_MAX = 500
    _TERMINAL_STATUSES = frozenset(
        ["completed", "failed", "error", "cancelled", "canceled"]
    )
    _SESSION_KEYS = frozenset(
        ["sessionId", "session_id", "nestedSessionId", "nested_session_id"]
    )

    def __init__(self):
        self.text_parts: list[str] = []
        self.thinking_parts: list[str] = []
        self.tool_calls: dict[str, ToolCallRecord] = {}
        self.active_tool_calls: dict[str, ToolCallRecord] = {}
        self.stop_reason: str = ""
        self.last_update_time: float = 0.0
        self.structured_result: StructuredResult | None = None
        self._required_output_tool: str | None = None

        self.session_id: str | None = None
        self.message_id: str | None = None
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.last_event_type: str | None = None
        self.last_event_at: str | None = None
        self.last_message_preview: str | None = None
        self.last_thought_preview: str | None = None

    def _now_iso(self) -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    def mark_update(self) -> None:
        self.last_update_time = time.monotonic()

    def _truncate_preview(self, text: str) -> str:
        if len(text) <= self.PREVIEW_MAX:
            return text
        return text[-self.PREVIEW_MAX :]

    @classmethod
    def _extract_nested_session_id(cls, data: Any) -> str | None:
        if isinstance(data, dict):
            for key in cls._SESSION_KEYS:
                if key in data and isinstance(data[key], str):
                    return data[key]
            for value in data.values():
                if (result := cls._extract_nested_session_id(value)):
                    return result
        elif isinstance(data, list):
            for item in data:
                if (result := cls._extract_nested_session_id(item)):
                    return result
        return None

    @staticmethod
    def _payload_to_dict(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            # MCP tool output format: {"output": "{...}", "metadata": {...}}
            if "output" in payload:
                output_val = payload["output"]
                if isinstance(output_val, str):
                    try:
                        import json
                        output_val = json.loads(output_val)
                    except (json.JSONDecodeError, ValueError):
                        pass
                if isinstance(output_val, dict):
                    if set(output_val.keys()) == {"result"} and isinstance(output_val["result"], dict):
                        return output_val["result"]
                    return output_val
            # Direct result format
            if set(payload.keys()) == {"result"} and isinstance(payload["result"], dict):
                return payload["result"]
            return payload
        if payload is None:
            return {}
        return {"value": payload}

    def set_required_output_tool(self, tool_name: str | None) -> None:
        self._required_output_tool = tool_name

    def _maybe_capture_structured_result(
        self,
        update: ToolCallStart | ToolCallProgress,
        payload: Any,
        *,
        overwrite: bool = False,
        title: str | None = None,
    ) -> None:
        if not self._required_output_tool:
            return
        actual_title = title or update.title
        expected_title = f"{CELLOS_MCP_SERVER}_{self._required_output_tool}"
        if actual_title not in {self._required_output_tool, expected_title}:
            return
        if self.structured_result is not None and not overwrite:
            return
        self.structured_result = StructuredResult(
            kind=self._required_output_tool,
            data=self._payload_to_dict(payload),
            source="tool_call",
            tool_call_id=update.tool_call_id,
            tool_name=actual_title,
        )

    def on_message_chunk(self, chunk: AgentMessageChunk) -> None:
        content = getattr(chunk, "content", None)
        if content and hasattr(content, "text"):
            text = content.text
            if text:
                logger.debug("message_chunk: %s", _debug_truncate(text))
                self.text_parts.append(text)
                self.last_message_preview = self._truncate_preview(text)

        self.last_event_type = "AgentMessageChunk"
        self.last_event_at = self._now_iso()

    def on_thought_chunk(self, chunk: AgentThoughtChunk) -> None:
        content = getattr(chunk, "content", None)
        if content and hasattr(content, "text"):
            logger.debug("thought_chunk: %s", _debug_truncate(content.text))
            self.thinking_parts.append(content.text)
            self.last_thought_preview = self._truncate_preview(content.text)

        self.last_event_type = "AgentThoughtChunk"
        self.last_event_at = self._now_iso()

    def on_tool_start(self, update: ToolCallStart) -> None:
        now = self._now_iso()
        raw_input = update.raw_input or {}
        nested_id = self._extract_nested_session_id(raw_input)
        rec = ToolCallRecord(
            tool_call_id=update.tool_call_id,
            title=update.title or "",
            status=update.status or "running",
            raw_input=raw_input,
            started_at=now,
            nested_session_id=nested_id,
        )
        self.tool_calls[update.tool_call_id] = rec
        self.active_tool_calls[update.tool_call_id] = rec
        self._maybe_capture_structured_result(update, raw_input)
        logger.debug(
            "tool_start id=%s title=%s nested_id=%s input=%s",
            update.tool_call_id,
            update.title or "",
            nested_id,
            _debug_truncate(raw_input),
        )
        self.last_event_type = "ToolCallStart"
        self.last_event_at = now

    def on_tool_progress(self, update: ToolCallProgress) -> None:
        rec = self.tool_calls.get(update.tool_call_id)
        if rec:
            rec.status = update.status or ""
            rec.raw_output = update.raw_output
            rec.updated_at = self._now_iso()
            raw_output = update.raw_output
            if not rec.nested_session_id and raw_output:
                rec.nested_session_id = self._extract_nested_session_id(raw_output)
            if update.status and update.status.lower() in self._TERMINAL_STATUSES:
                self.active_tool_calls.pop(update.tool_call_id, None)
            self._maybe_capture_structured_result(
                update, raw_output, overwrite=True, title=rec.title
            )
            logger.debug(
                "tool_progress id=%s status=%s nested_id=%s output=%s",
                update.tool_call_id,
                update.status or "",
                rec.nested_session_id,
                _debug_truncate(raw_output),
            )
        self.last_event_type = "ToolCallProgress"
        self.last_event_at = self._now_iso()

    def to_result(self) -> AcpRunResult:
        text = "".join(self.text_parts)
        thinking = "".join(self.thinking_parts)

        logger.debug(
            "to_result text=%d thinking=%d tools=%d active=%d stop=%s",
            len(text),
            len(thinking),
            len(self.tool_calls),
            len(self.active_tool_calls),
            self.stop_reason,
        )

        return AcpRunResult(
            text=text,
            thinking=thinking,
            tool_calls=list(self.tool_calls.values()),
            active_tool_calls=list(self.active_tool_calls.values()),
            structured_result=self.structured_result,
            stop_reason=self.stop_reason,
            session_id=self.session_id,
            message_id=self.message_id,
            started_at=self.started_at,
            completed_at=self.completed_at,
            last_event_at=self.last_event_at,
            last_event_type=self.last_event_type,
            last_message_preview=self.last_message_preview,
            last_thought_preview=self.last_thought_preview,
        )


class _AcpClientImpl(Client):
    """ACP Client interface implementation backed by an EventCollector."""

    def __init__(self, auto_approve: bool = True):
        self.collector = _EventCollector()
        self.auto_approve = auto_approve
        self._on_event = None

    def set_on_event(self, callback) -> None:
        self._on_event = callback

    async def session_update(
        self, session_id: str, update: Any, **kwargs: Any
    ) -> None:
        update_type = type(update).__name__
        logger.debug("session_update session=%s type=%s", session_id, update_type)
        if isinstance(update, AgentMessageChunk):
            self.collector.mark_update()
            self.collector.on_message_chunk(update)
        elif isinstance(update, AgentThoughtChunk):
            self.collector.mark_update()
            self.collector.on_thought_chunk(update)
        elif isinstance(update, ToolCallStart):
            self.collector.mark_update()
            self.collector.on_tool_start(update)
        elif isinstance(update, ToolCallProgress):
            self.collector.mark_update()
            self.collector.on_tool_progress(update)

        if self._on_event:
            col = self.collector
            event_dict = {
                "session_id": col.session_id,
                "message_id": col.message_id,
                "event_type": update_type,
                "event_at": col.last_event_at,
                "text_preview": col.last_message_preview,
                "thinking_preview": col.last_thought_preview,
            }
            tool_call_id = getattr(update, "tool_call_id", None)
            tool_rec = col.tool_calls.get(tool_call_id) if tool_call_id else None
            if tool_rec:
                event_dict["tool_call"] = {
                    "tool_call_id": tool_rec.tool_call_id,
                    "title": tool_rec.title,
                    "status": tool_rec.status,
                    "nested_session_id": tool_rec.nested_session_id,
                }
            try:
                if asyncio.iscoroutinefunction(self._on_event):
                    await self._on_event(event_dict)
                else:
                    self._on_event(event_dict)
            except Exception as cb_err:
                logger.debug("on_event callback error: %s", cb_err)

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
                    outcome=DeniedOutcome(outcome="cancelled")
                )
            logger.debug("permission auto-approved: option=%s", allow_id)
            return RequestPermissionResponse(
                outcome=AllowedOutcome(outcome="selected", option_id=allow_id)
            )
        logger.debug("permission denied (auto_approve=False)")
        return RequestPermissionResponse(
            outcome=DeniedOutcome(outcome="cancelled")
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
        model: str | None = None,
        hermes_profile: str | None = None,
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
            model: Optional opencode model name.
            hermes_profile: Optional Hermes profile name for per-run ACP launch.
            auto_approve: Auto-approve all permission requests.
            timeout: Total timeout in seconds for the entire lifecycle.
            text_wait: Seconds of idle time after the latest streaming update before
                returning. Set to 0 to disable. Default 1.0 for agents that send
                chunks after result.
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
            if agent == "hermes" and hermes_profile:
                self._args = ["-p", hermes_profile, *self._args]

        self._cwd = cwd
        self._env = {**adapter_env, **(env or {})}
        if model and "OPENCODE_CONFIG_CONTENT" not in self._env:
            self._env["OPENCODE_CONFIG_CONTENT"] = json.dumps({"model": model})
        self._auto_approve = auto_approve
        self._timeout = timeout
        self._text_wait = text_wait
        self._model = model
        self._hermes_profile = hermes_profile

        logger.debug(
            "AcpClient init command=%s args=%s cwd=%s timeout=%s text_wait=%s auto_approve=%s",
            self._command,
            self._args,
            self._cwd,
            self._timeout,
            self._text_wait,
            self._auto_approve,
        )

    async def run(
        self,
        prompt: str,
        output_tools=None,
        required_output_tool: str | None = None,
        on_event=None,
    ) -> AcpRunResult:
        """Execute a prompt against the agent and return the result.

        After the prompt response arrives, waits until streaming updates have been
        idle for `text_wait` seconds (opencode sends chunks after result).
        """

        if on_event is None and callable(output_tools) and required_output_tool is None:
            on_event = output_tools
            output_tools = None

        impl = _AcpClientImpl(
            auto_approve=self._auto_approve,
        )
        impl.collector.set_required_output_tool(required_output_tool)
        if on_event:
            impl.set_on_event(on_event)

        async def _execute() -> AcpRunResult:
            env = dict(self._env) if self._env else None
            cmd_line = [self._command, *self._args]
            mcp_server_proc = None

            logger.debug("spawning %s cwd=%s env=%s", cmd_line, self._cwd, env)

            try:
                if output_tools:
                    mcp_server_proc = spawn_mcp_server(output_tools)

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
                    session_kwargs = {"cwd": self._cwd}
                    if mcp_server_proc:
                        session_kwargs["mcp_servers"] = [mcp_server_proc.mcp_server]
                    session = await conn.new_session(**session_kwargs)
                    impl.collector.session_id = session.session_id
                    impl.collector.started_at = impl.collector._now_iso()
                    logger.debug("session created id=%s", session.session_id)

                    # Send prompt
                    msg_id = str(uuid4())
                    impl.collector.message_id = msg_id
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

                    # Wait until late events go idle (opencode sends chunks after result).
                    if self._text_wait > 0:
                        drain_start = time.monotonic()
                        idle_since = max(impl.collector.last_update_time, drain_start)
                        max_wait = min(self._text_wait * 5, 30.0)
                        logger.debug(
                            "waiting for late chunks idle=%.1fs max=%.1fs",
                            self._text_wait,
                            max_wait,
                        )
                        while True:
                            now = time.monotonic()
                            latest_update = max(
                                impl.collector.last_update_time, idle_since
                            )
                            if latest_update != idle_since:
                                idle_since = latest_update
                                logger.debug("late chunk observed; resetting idle wait")
                            if now - idle_since >= self._text_wait:
                                logger.debug("late chunks idle for %.1fs", self._text_wait)
                                break
                            if now - drain_start >= max_wait:
                                logger.warning(
                                    "late chunk drain timed out after %.1fs", max_wait
                                )
                                break
                            await asyncio.sleep(0.05)

                    result = impl.collector.to_result()
                    result.completed_at = impl.collector._now_iso()
                    return result
            finally:
                if mcp_server_proc:
                    try:
                        mcp_server_proc.proc.terminate()
                    except ProcessLookupError:
                        pass
                    try:
                        mcp_server_proc.proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try:
                            mcp_server_proc.proc.kill()
                        except ProcessLookupError:
                            pass

        if self._timeout:
            try:
                return await asyncio.wait_for(_execute(), timeout=self._timeout)
            except asyncio.TimeoutError as exc:
                result = impl.collector.to_result()
                result.error = TimeoutError(f"ACP timeout after {self._timeout}s")
                result.timeout = True
                result.error_type = "TimeoutError"
                result.error_message = str(result.error)
                result.completed_at = impl.collector._now_iso()
                logger.error(
                    "ACP timeout after %.1fs (last_event=%s active_tools=%d)",
                    self._timeout,
                    result.last_event_type,
                    len(result.active_tool_calls),
                    exc_info=True,
                )
                return result
            except Exception as e:
                result = impl.collector.to_result()
                result.error = e
                result.error_type = type(e).__name__
                result.error_message = str(e)
                result.completed_at = impl.collector._now_iso()
                logger.error("execution error: %s", e, exc_info=True)
                return result
        try:
            return await _execute()
        except Exception as e:
            result = impl.collector.to_result()
            result.error = e
            result.error_type = type(e).__name__
            result.error_message = str(e)
            result.completed_at = impl.collector._now_iso()
            logger.error("execution error: %s", e, exc_info=True)
            return result
