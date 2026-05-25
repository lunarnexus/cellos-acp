# cellos-acp

Lightweight ACP client with multi-agent adapters. Wraps the official [`agent-client-protocol`](https://github.com/agentclientprotocol/python-sdk) Python SDK, adding adapter management, result normalization, and a CLI.

Designed as a standalone library — import it, pick an adapter, call `run(prompt)`, get back a unified `AcpRunResult`.

## Quick start

```bash
# Install
pipx install ./cellos-acp

# List available agents
cellos-acp list

# Run a prompt
cellos-acp run --agent opencode "What is 2+2?"

# Text-only output
cellos-acp run --quiet "What is 2+2?"

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
│   ├── AgentRegistry → maps names to commands/args/quirks
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
| Adapter quirks (thought_only) | ❌ | Per-adapter config |
| Unified `AcpRunResult` | ❌ | `.text`, `.thinking`, `.tool_calls` |
| Late-chunk handling | ❌ | Configurable quiet wait |
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
  opencode      opencode acp                              thought_only=True
  claude        claude --experimental-acp                 thought_only=False
  codex         codex --acp                               thought_only=False
  hermes        hermes acp                                thought_only=False
  openclaw      acpx openclaw exec                        thought_only=False
  pi            pi acp                                    thought_only=False
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
| `--quiet-wait` | `1.0` | Seconds to wait for late streaming chunks (0 to disable) |
| `--no-approve` | `false` | Don't auto-approve permission requests |
| `--thought-only` | `false` | Force thought-only mode (promote thinking → text) |
| `--json` | `false` | Output result as JSON |
| `--quiet` | `false` | Only print combined text |

**Examples:**

```bash
# Default (verbose text output)
cellos-acp run "Explain this code"

# Quiet mode — text only
cellos-acp run --quiet "What is 2+2?"

# JSON output — structured result
cellos-acp run --json "What is 2+2?"

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
        thought_only=None,      # force thought-only mode (auto from adapter)
        auto_approve=True,      # auto-approve permission requests
        timeout=300,            # total timeout in seconds (None = no timeout)
        quiet_wait=1.0,         # seconds to wait for late streaming chunks
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
    status: str          # "running", "completed", "failed"
    raw_input: dict
    raw_output: Any
```

### Registry

```python
from cellos_acp import get_adapter, AgentRegistry, AgentAdapter

# Get a registered adapter
adapter = get_adapter("opencode")
print(adapter.full_command())  # ["opencode", "acp"]

# Register a custom adapter
registry = AgentRegistry()
registry.register(AgentAdapter(
    name="my-agent",
    command="my-agent",
    args=["--acp-mode"],
    quirks={"thought_only": False},
))
# Now available as: AcpClient(agent="my-agent")
```

## Adapters

### Built-in

| Name | Command | Quirks | Status |
|---|---|---|---|
| `opencode` | `opencode acp` | `thought_only=True` | ✅ Working |
| `claude` | `claude --experimental-acp` | — | Future |
| `codex` | `codex --acp` | — | Future |
| `hermes` | `hermes acp` | — | Future |
| `openclaw` | `acpx openclaw exec` | — | Future |
| `pi` | `pi acp` | — | Future |

> **Note:** Only `opencode` is currently tested and working. Other adapters are placeholders for future integration.

### `thought_only` mode

Some agents route ALL content through `AgentThoughtChunk` events with zero `AgentMessageChunk` events. When `thought_only=True`, the collector promotes thinking → text so `.combined_text` returns the actual response.

### Late streaming chunks

Some agents send chunks AFTER the `PromptResponse` arrives. `cellos-acp` waits `quiet_wait` seconds (default 1.0) after the response to catch late events. Set to 0 to disable.

## Testing

```bash
# Smoke tests
cd ./cellos-acp
# See SMOKETEST.md for full test suite

# Quick check
cellos-acp run --quiet "Respond with exactly: SMOKE_OK"
```

## Dependencies

- [`agent-client-protocol`](https://pypi.org/project/agent-client-protocol/) — official ACP Python SDK
- [`click`](https://click.palletsprojects.com/) — CLI framework

## License

MIT
