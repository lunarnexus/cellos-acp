# cellos-acp

Lightweight ACP client with multi-agent adapters. Wraps the official [`agent-client-protocol`](https://github.com/agentclientprotocol/python-sdk) Python SDK, adding adapter management, result normalization, and a CLI tester.

Designed as a standalone library for [CelloS](https://github.com/) — the orchestrator imports it, picks an adapter, calls `run(prompt)`, and gets back a unified `AcpRunResult`.

## Quick start

```bash
# Install
pipx install ~/workspace/cellos-acp

# List available agents
cellos-acp list

# Run a prompt
cellos-acp run --agent opencode "What is 2+2?"

# Text-only output
cellos-acp run --agent opencode --quiet "What is 2+2?"

# JSON output
cellos-acp run --agent opencode --json "What is 2+2?"
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

**What `cellos-acp` adds over the raw SDK:**

| Feature | SDK | cellos-acp |
|---|---|---|
| Subprocess + JSON-RPC framing | ✅ | Uses it |
| Schema models (Pydantic) | ✅ | Uses them |
| Agent registry | ❌ | Built-in + extensible |
| Adapter quirks (thought_only) | ❌ | Per-adapter config |
| Unified `AcpRunResult` | ❌ | `.text`, `.thinking`, `.tool_calls` |
| Late-chunk handling | ❌ | 1s quiet wait after response |
| Auto-approve permissions | ❌ | Configurable default |
| CLI tester | ❌ | `cellos-acp run/list` |

## Installation

### Development (editable)

```bash
cd ~/workspace/cellos-acp
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[test]"
```

### System-wide via pipx

```bash
pipx install ~/workspace/cellos-acp
cellos-acp --help    # available everywhere
```

After making code changes:

```bash
pipx install --force ~/workspace/cellos-acp
```

Uninstall:

```bash
pipx uninstall cellos-acp
```

### Direct module (no install)

```bash
cd ~/workspace/cellos-acp
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

**Arguments:**

| Option | Default | Description |
|---|---|---|
| `PROMPT` | *(required)* | Prompt text to send to the agent |
| `--agent`, `-a` | `opencode` | Registered adapter name |
| `--custom-cmd` | *(none)* | Override command (ignores adapter) |
| `--custom-args` | *(none)* | Override args (repeatable, ignores adapter) |
| `--cwd` | `.` | Working directory for the agent |
| `--timeout` | `120` | Total timeout in seconds |
| `--no-approve` | `false` | Don't auto-approve permission requests |
| `--json` | `false` | Output result as JSON |
| `--quiet` | `false` | Only print combined text |

**Examples:**

```bash
# Default (verbose text output)
cellos-acp run "Explain this code" --file code.py

# Quiet mode — text only
cellos-acp run --quiet "What is 2+2?"

# JSON output — structured result
cellos-acp run --json "What is 2+2?"

# Custom command (unregistered agent)
cellos-acp run --custom-cmd my-agent --custom-args --acp "Hello"

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

## Programmatic API

### `AcpClient`

```python
import asyncio
from cellos_acp import AcpClient

async def main():
    client = AcpClient(
        agent="opencode",       # registered adapter name
        cwd="/tmp/project",     # working directory
        auto_approve=True,      # auto-approve permissions
        timeout=120,            # total timeout in seconds
    )
    result = await client.run("Explain the codebase")

    print(result.combined_text)   # text or thinking
    print(result.text)            # from AgentMessageChunk
    print(result.thinking)        # from AgentThoughtChunk
    print(result.tool_calls)      # list of ToolCallRecord
    print(result.stop_reason)     # e.g. "end_turn"
    print(result.success)         # True if no error

asyncio.run(main())
```

**Constructor parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent` | `str` | `"opencode"` | Registered adapter name |
| `command` | `str` | *(from adapter)* | Override command (ignores adapter) |
| `args` | `list[str]` | *(from adapter)* | Override args (ignores adapter) |
| `cwd` | `str` | `"."` | Working directory |
| `env` | `dict[str, str]` | `None` | Extra environment variables |
| `thought_only` | `bool` | *(from adapter)* | Force thought-only mode |
| `auto_approve` | `bool` | `True` | Auto-approve permission requests |
| `timeout` | `float` | `None` | Total timeout in seconds |

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

### `AgentAdapter`

```python
@dataclass
class AgentAdapter:
    name: str                       # "opencode"
    command: str                    # "opencode"
    args: list[str]                 # ["acp"]
    env: dict[str, str]             # extra env vars
    quirks: dict[str, Any]          # adapter-specific flags
```

## Adapters

### Built-in adapters

| Name | Command | Quirks | Notes |
|---|---|---|---|
| `opencode` | `opencode acp` | `thought_only=True` | All content via `AgentThoughtChunk` |
| `claude` | `claude --experimental-acp` | — | Anthropic reference format |
| `codex` | `codex --acp` | — | OpenAI Codex CLI |
| `hermes` | `hermes acp` | — | Hermes Agent |
| `openclaw` | `acpx openclaw exec` | — | Via acpx proxy |
| `pi` | `pi acp` | — | Pi agent |

### `thought_only` mode

Some agents (notably opencode with LMStudio) route ALL content through `AgentThoughtChunk` events with zero `AgentMessageChunk` events. When `thought_only=True`, the collector promotes thinking → text so `.combined_text` returns the actual response.

This is **expected adapter behavior**, not a bug. The thinking text IS the answer.

### Adding custom adapters

```python
from cellos_acp import AgentRegistry
from cellos_acp.registry import AgentAdapter

my_adapter = AgentAdapter(
    name="my-agent",
    command="my-agent",
    args=["--acp-mode"],
    env={"MY_API_KEY": "secret"},
    quirks={"thought_only": False},
)

AgentRegistry().register(my_adapter)
# Now available as: AcpClient(agent="my-agent")
```

Or via CLI:

```bash
cellos-acp run --custom-cmd my-agent --custom-args --acp-mode "Hello"
```

## Testing

```bash
# Unit tests
cd ~/workspace/cellos-acp
source .venv/bin/activate
pytest tests/ -v

# Smoke test against real agent
cellos-acp run --agent opencode --quiet "Respond with exactly: SMOKE_OK"
```

## Adapter quirks

### Opencode + LMStudio: thinking-only output

When using opencode with LMStudio models, the agent ONLY outputs `agent_thought_chunk` events. Each chunk is a streaming fragment — concatenate ALL chunks in order to reconstruct the full text.

**How cellos-acp handles it:** The `thought_only=True` quirk on the opencode adapter promotes thinking → text automatically.

### Late streaming chunks

Some agents send thinking chunks AFTER the `PromptResponse` arrives. The SDK returns on `stop_reason` without waiting. `cellos-acp` adds a 1-second quiet wait after the response to catch late events.

### Stdout debug output

Opencode's LMStudio plugin writes non-JSON lines to stdout (e.g., `[opencode-lmstudio] LM Studio plugin initialized`). The SDK's receive loop skips these gracefully — no action needed.

## Integration with CelloS

```python
from cellos_acp import AcpClient, AcpRunResult

async def delegate_to_agent(task: str, agent: str = "opencode") -> AcpRunResult:
    client = AcpClient(
        agent=agent,
        cwd=task.workdir,
        auto_approve=True,
        timeout=task.timeout_seconds,
    )
    return await client.run(task.prompt)
```

## Dependencies

- [`agent-client-protocol`](https://pypi.org/project/agent-client-protocol/) — official ACP Python SDK (JSON-RPC framing, schema models, subprocess wiring)
- [`click`](https://click.palletsprojects.com/) — CLI framework

## License

MIT
