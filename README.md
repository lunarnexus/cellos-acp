# cellos-acp

Lightweight ACP client with multi-agent adapters. Wraps the official [`agent-client-protocol`](https://github.com/agentclientprotocol/python-sdk) Python SDK, adding adapter management, result normalization, and a CLI.

Designed as a standalone library — import it, pick an adapter, call `run(prompt)`, get back a unified `AcpRunResult`.

This was actually built to work with Cellos (https://github.com/lunarnexus/cellos/) to handle ACP calls, but it's generic enough to work with almost anything.

## Quick start

```bash
# Install
pipx install ./cellos-acp

# List available agents
cellos-acp list

# Run a prompt
cellos-acp run --agent opencode "What is 2+2?"

# Text-only output
cellos-acp run --text "What is 2+2?"

# JSON output
cellos-acp run --json "What is 2+2?"
```

## Architecture

```
cellos-acp
├── CLI Layer (Click)
│   └── cellos-acp run/list
│
├── AcpClient
│   ├── AgentRegistry → maps names to commands/args/env
│   ├── _EventCollector → accumulates events into AcpRunResult
│   └── _AcpClientImpl → implements ACP Client interface
│
└── agent-client-protocol SDK (dependency)
    ├── spawn_agent_process() → subprocess + stdio wiring
    ├── ClientSideConnection → JSON-RPC 2.0 framing
    └── Pydantic schema models → typed ACP messages
```

**What `cellos-acp` adds over the raw `agent-client-protocol` library:**

| Feature | agent-client-protocol | cellos-acp |
|---|---|---|
| Subprocess + JSON-RPC framing | ✅ | Uses it |
| Schema models (Pydantic) | ✅ | Uses them |
| Agent registry | ❌ | Built-in + extensible |
| Unified `AcpRunResult` | ❌ | `.text`, `.thinking`, `.tool_calls` |
| Late-chunk handling | ❌ | Configurable idle drain |
| Auto-approve permissions | ❌ | Configurable default |
| CLI | ❌ | `cellos-acp run/list` |

## Installation

### System-wide via pipx

```bash
pipx install ./cellos-acp
```

Reinstall after changes:

```bash
pipx uninstall cellos-acp && pipx install ./cellos-acp
```

### Development (editable)

```bash
cd ./cellos-acp
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[test]"
```

### Direct module (no install)

```bash
cd ./cellos-acp
python3 -m cellos_acp --help
```

## CLI Reference

### `cellos-acp list`

List available agent adapters:

```bash
$ cellos-acp list
  opencode      opencode acp
  claude        claude --experimental-acp
  codex         codex --acp
  hermes        hermes acp
  openclaw      acpx openclaw exec
  pi            pi acp
```

### `cellos-acp run`

Execute a prompt against an ACP agent.

```
cellos-acp run [OPTIONS] PROMPT
```

**Options:**

| Option | Default | Description |
|---|---|---|
| `--agent`, `-a` | `opencode` | Registered adapter name |
| `--custom-cmd` | *(none)* | Override command (ignores adapter) |
| `--custom-args` | *(none)* | Override args (repeatable, ignores adapter) |
| `--cwd` | `.` | Working directory for the agent |
| `--timeout` | `300` | Total timeout in seconds |
| `--text-wait` | `1.0` | Idle seconds to wait for late streaming chunks (0 to disable) |
| `--no-approve` | `false` | Don't auto-approve permission requests |
| `--json` | `false` | Output result as JSON |
| `--text` | `false` | Only print combined text |
| `--log-file` | *(none)* | Path to debug log file (opt-in) |

**Examples:**

```bash
# Default (verbose text output)
cellos-acp run "Explain this code"

# Text-only mode — text only
cellos-acp run --text "What is 2+2?"

# JSON output — structured result
cellos-acp run --json "What is 2+2?"

# With debug log file
cellos-acp run --log-file /tmp/my-log.log "What is 2+2?"

# Custom command (unregistered agent)
cellos-acp run --custom-cmd my-agent --custom-args --acp-mode "Hello"

# With timeout and working directory
cellos-acp run --cwd /tmp/project --timeout 60 "Fix the tests"
```

**Verbose output format:**

```
--- text (42 chars) ---
The answer is 4.

--- thinking (120 chars) ---
The user wants me to answer what 2+2 is...

--- tool calls (0) ---

--- stop: end_turn ---
```

If `text` is empty, shows `(empty)` instead. If `thinking` is empty, that section is omitted entirely.

**Debug logging:**

Pass `--log-file` to write debug logs to a file. Logs include errors, process spawn details, session IDs, prompt data, event chunks, tool calls, and permission decisions. Long content is truncated with a `[TRUNCATED: N chars total]` marker. Logs go only to the file — they never appear in CLI output or affect Python return values.

```bash
# Check the log after a run
cat /tmp/cellos-acp.log

# Custom log path
cellos-acp run --log-file /var/log/my-agent.log "hello"
```

**JSON output format:**

```json
{
  "text": "The answer is 4.",
  "thinking": "The user wants me to...",
  "tool_calls": [],
  "stop_reason": "end_turn",
  "error": null,
  "success": true
}
```

## Python API

### Basic usage

```python
import asyncio
from cellos_acp import AcpClient

async def main():
    result = await AcpClient(agent="opencode").run("What is 2+2?")
    print(result.combined_text)  # "4" or "The answer is 4."

asyncio.run(main())
```

### Full constructor

```python
import asyncio
from cellos_acp import AcpClient

async def main():
    client = AcpClient(
        agent="opencode",       # registered adapter name
        command=None,           # override command (ignores adapter)
        args=None,              # override args (ignores adapter)
        cwd="/tmp/project",     # working directory
        env={"VAR": "val"},     # extra environment variables
        auto_approve=True,      # auto-approve permission requests
        timeout=300,            # total timeout in seconds (None = no timeout)
        text_wait=1.0,          # idle seconds to wait for late streaming chunks
    )
    result = await client.run("Explain the codebase")

asyncio.run(main())
```

### `AcpRunResult`

```python
@dataclass
class AcpRunResult:
    text: str                    # from AgentMessageChunk events
    thinking: str                # from AgentThoughtChunk events
    tool_calls: list[ToolCallRecord]  # tool call records
    stop_reason: str             # e.g. "end_turn"
    error: Exception | None      # exception if failed

    @property
    def success(self) -> bool:   # True if error is None
    @property
    def combined_text(self) -> str:  # text or thinking
```

### `ToolCallRecord`

```python
@dataclass
class ToolCallRecord:
    tool_call_id: str
    title: str
    status: str          # latest status from tool progress events, or ""
    raw_input: dict
    raw_output: Any
```

### Registry

```python
from cellos_acp import AgentAdapter
from cellos_acp.registry import _registry

# Register a custom adapter (uses the global registry)
_registry.register(AgentAdapter(
    name="my-agent",
    command="my-agent",
    args=["--acp-mode"],
))
# Now available as: AcpClient(agent="my-agent")
```

### Logging

Enable file-based debug logging with `configure_logging()`. Logs go only to a file — they never affect stdout or Python return values.

```python
from cellos_acp import configure_logging, AcpClient

# Configure logging to a file
log_file = configure_logging("/tmp/my-agent.log")
```

Logs include client initialization, process spawn, session creation, prompt data, event chunks, tool calls, permission decisions, and errors with full tracebacks. Long content is truncated with a `[TRUNCATED: N chars total]` marker.

## Adapters

### Built-in

| Name | Command | Status |
|---|---|---|
| `opencode` | `opencode acp` | ✅ Working |
| `claude` | `claude --experimental-acp` | Future |
| `codex` | `codex --acp` | Future |
| `hermes` | `hermes acp` | Future |
| `openclaw` | `acpx openclaw exec` | Future |
| `pi` | `pi acp` | Future |

> **Note:** Only `opencode` is currently tested and working. Other adapters are placeholders for future integration.

### Late streaming chunks

Some agents send chunks AFTER the `PromptResponse` arrives. `cellos-acp` waits until late streaming updates have been idle for `text_wait` seconds (default 1.0) before returning. The idle drain has a hard cap of 5x `text_wait`, up to 30 seconds, to avoid hanging if an agent keeps streaming. Set `text_wait=0` to disable. The Python API default timeout is 300 seconds; pass `timeout=None` for no timeout.

## Testing

```bash
# Smoke tests
cd ./cellos-acp
# See SMOKETEST.md for full test suite

# Quick check
cellos-acp run --text "Respond with exactly: SMOKE_OK"

# Unit tests
cd ./cellos-acp
uv run pytest tests/test_client.py -v

# E2E tests (requires opencode)
cd ./cellos-acp
uv run pytest tests/test_e2e.py -v --timeout=30
```

## Dependencies

- [`agent-client-protocol`](https://pypi.org/project/agent-client-protocol/) — official ACP Python SDK
- [`click`](https://click.palletsprojects.com/) — CLI framework

## License

MIT
