# cellos-acp Smoke Tests

**Process:**
The user wants you to step through each step one-by-one.  Before each step, list
 the step and commands, what the step proves, what we should expect to see, then
 pause for the user go-ahead.  After approval, run the test step, list all test
outputs.
If there's a failure, stop the test and explain, don't attempt to fix anything.

All tests use `opencode` (default agent). Steps 1-6, 13-14, 17, 23 are CLI. Steps 7-12, 15-16, 18-22, 24 are Python API (run from project dir with `uv run`). Steps 10-11 are unit tests.

## Prerequisites

```bash
pipx uninstall cellos-acp && pipx install /path/to/cellos-acp
```

**Expected:** Fresh install of current source. This ensures the CLI binary matches the code you're testing — stale pipx installs are a common source of false failures (e.g. old `--quiet-wait` vs new `--text-wait`).

```bash
which cellos-acp && which opencode
```

**Expected:** Both return paths.

---

## 1. CLI: List adapters

```bash
cellos-acp list
```

**Expected:** 6 agents listed with commands.

---

## 2. CLI: Simple prompt

```bash
cellos-acp run "Say hello in three words" --text
```

**Expected:** A short greeting, no headers.

---

## 3. CLI: JSON output

```bash
cellos-acp run "Reply with the number four" --json
```

**Expected:** Valid JSON with `success: true`, `text` containing "4", and a `diagnostics` block containing `session_id`, `message_id`, `started_at`, `completed_at`, `last_event_type`, `timeout: false`, `aborted: false`, and `active_tool_calls: []`.

---

## 4. CLI: Custom command (bypass registry)

```bash
cellos-acp run "Say hi" --custom-cmd opencode --custom-args acp --timeout 60 --text
```

**Expected:** A greeting.

---

## 5. CLI: Timeout (preserves partial state)

```bash
cellos-acp run "Write a detailed 500-word essay about the history of computing" --timeout 2 --json
```

**Expected:** JSON with `success: false`, `error` containing "timeout", and `diagnostics` with `timeout: true`, `error_type: "TimeoutError"`, `session_id`, `message_id`, `started_at`, `completed_at`, and `last_event_type`. The `text` and `thinking` fields may contain partial output collected before the timeout.

> **Note:** If agent startup is fast on your machine, the prompt may complete in 2s. Increase `--timeout` to a value lower than expected generation time, or use a longer prompt.

---

## 6. CLI: No auto-approve

```bash
cellos-acp run "Say something brief" --no-approve --text
```

**Expected:** Agent responds without crashing.

---

## 7. Python API: Import and run

Run from project directory (`cd cellos-acp` first):

```bash
uv run python3 -c "
import asyncio
from cellos_acp import AcpClient, AcpRunResult

async def main():
    result = await AcpClient(agent='opencode').run('What color is the sky?')
    assert result.success and 'blue' in result.combined_text.lower()
    print(f'OK: {len(result.combined_text)} chars')

asyncio.run(main())
"
```

**Expected:** `OK: N chars`

---

## 8. Python API: combined_text fallback

```bash
uv run python3 -c "
import asyncio
from cellos_acp import AcpClient

async def main():
    result = await AcpClient(agent='opencode').run('Name a fruit')
    assert result.combined_text, 'combined_text should not be empty'
    print(f'OK: {repr(result.combined_text[:50])}')

asyncio.run(main())
"
```

**Expected:** `combined_text` populated (prefers `text`, falls back to `thinking`).

---

## 9. Python API: Timeout (preserves partial state)

```bash
uv run python3 -c "
import asyncio
from cellos_acp import AcpClient

async def main():
    result = await AcpClient(agent='opencode', timeout=30, text_wait=0).run('Write a very long response')
    assert not result.success
    assert result.timeout is True
    assert result.error_type == 'TimeoutError'
    assert result.session_id is not None
    assert result.message_id is not None
    assert result.started_at is not None
    assert result.completed_at is not None
    print(f'OK: timeout handled (session={result.session_id}, text={len(result.text)} chars)')

asyncio.run(main())
"
```

**Expected:** `OK: timeout handled (session=ses_..., text=N chars)` — timeout preserves partial state including session ID, message ID, timestamps, and any text/thinking collected before timeout.

> **Note:** Agent startup can be slow (~20s). Use `timeout=30` to ensure the agent initializes before timing out. Adjust if your machine is faster/slower.

---

## 10. Registry: Get adapter

```bash
uv run python3 -c "
from cellos_acp import get_adapter, AgentRegistry

adapter = get_adapter('opencode')
assert adapter.command == 'opencode' and adapter.args == ['acp']
print(f'OK: {adapter.full_command()}')

try:
    get_adapter('nonexistent')
except KeyError:
    print('OK: KeyError for unknown agent')

print(f'OK: {len(AgentRegistry().list_names())} adapters')
"
```

**Expected:** Three `OK:` lines.

---

## 11. Result dataclass

```bash
uv run python3 -c "
from cellos_acp import AcpRunResult, ToolCallRecord

assert AcpRunResult(text='hi').success and AcpRunResult(text='hi').combined_text == 'hi'
assert not AcpRunResult(error=RuntimeError('boom')).success
assert AcpRunResult(thinking='fallback').combined_text == 'fallback'

# Verify diagnostic fields exist with defaults
r = AcpRunResult(text='hi')
assert r.session_id is None
assert r.message_id is None
assert r.timeout is False
assert r.aborted is False
assert r.error_type is None
assert r.active_tool_calls == []

# Verify ToolCallRecord diagnostic fields
tc = ToolCallRecord(tool_call_id='tc_1', title='test')
assert tc.started_at is None
assert tc.updated_at is None
assert tc.nested_session_id is None
print('OK: result tests passed')
"
```

**Expected:** `OK: result tests passed`

---

## 12. Python API: text_wait=0

```bash
uv run python3 -c "
import asyncio
import time
from cellos_acp import AcpClient

async def main():
    start = time.monotonic()
    result = await AcpClient(agent='opencode', text_wait=0).run('Say hi')
    elapsed = time.monotonic() - start
    assert result.success
    print(f'OK: {elapsed:.1f}s (no extra wait)')

asyncio.run(main())
"
```

**Expected:** Completes quickly without the 1s text wait overhead.

---

## 13. CLI: --text-wait=0

```bash
cellos-acp run "Say hi" --text-wait 0 --text
```

**Expected:** A greeting, no headers, and no extra 1s text wait overhead.

---

## 14. CLI: --cwd option

```bash
cellos-acp run "What directory are you in?" --cwd /tmp --text
```

**Expected:** Agent responds (should mention /tmp or equivalent). Verifies `--cwd` is passed through.

---

## 15. Python API: env parameter

```bash
uv run python3 -c "
import asyncio
from cellos_acp import AcpClient

async def main():
    # env is merged with adapter env; verify it's accepted without error
    client = AcpClient(agent='opencode', env={'TEST_VAR': 'hello'})
    assert client._env.get('TEST_VAR') == 'hello'
    print('OK: env parameter accepted')

asyncio.run(main())
"
```

**Expected:** `OK: env parameter accepted`

---

## 16. Python API: Unknown agent error

```bash
uv run python3 -c "
from cellos_acp import AcpClient

try:
    AcpClient(agent='nonexistent')
    print('FAIL: should have raised KeyError')
except KeyError as e:
    assert 'nonexistent' in str(e)
    print('OK: unknown agent raises KeyError in __init__')
"
```

**Expected:** `OK: unknown agent raises KeyError in __init__`

---

## 17. CLI: Agent not found (binary missing)

```bash
cellos-acp run --custom-cmd nonexistent_binary --custom-args test "hi" --json
```

**Expected:** JSON with `success: false` and `error` containing information about the missing binary.

---

## 18. Python API: Tool call collection and active tool calls

```bash
uv run python3 -c "
import asyncio
from cellos_acp import AcpClient

async def main():
    result = await AcpClient(agent='opencode', timeout=120).run(
        'List files in the current directory. Use a tool if available.'
    )
    assert result.success
    print(f'OK: {len(result.tool_calls)} tool calls, {len(result.active_tool_calls)} active')
    for tc in result.tool_calls:
        print(f'  [{tc.status}] {tc.title} (started={tc.started_at})')

asyncio.run(main())
"
```

**Expected:** `OK: N tool calls, M active` (N may be 0 if agent doesn't use tools). `active_tool_calls` should be 0 if all tools completed. Tool calls include `started_at`, `updated_at`, and `nested_session_id` fields. Note: 120s timeout needed for agents that use tools.

---

## 19. CLI: Debug log file

```bash
cellos-acp run "Say hi" --log-file /tmp/cellos-smoketest.log --text
```

**Expected:** A greeting on stdout. `/tmp/cellos-smoketest.log` exists and contains debug entries.

```bash
cat /tmp/cellos-smoketest.log
```

**Expected:** Log file contains timestamps, DEBUG-level entries (spawn, session, prompt, events), and no `[TRUNCATED]` markers for this short prompt.

---

## 20. Python API: Logging configuration

```bash
uv run python3 -c "
import asyncio
from cellos_acp import configure_logging, AcpClient

log_file = configure_logging('/tmp/cellos-smoketest-py.log')
assert log_file == '/tmp/cellos-smoketest-py.log'

async def main():
    result = await AcpClient(agent='opencode', timeout=30).run('Say hi')
    assert result.success
    print('OK: run completed with logging enabled')

asyncio.run(main())
"
```

**Expected:** `OK: run completed with logging enabled`. `/tmp/cellos-smoketest-py.log` exists with debug entries.

```bash
cat /tmp/cellos-smoketest-py.log
```

**Expected:** Log file contains DEBUG entries for client init, spawn, session, prompt, and events.

---

## 21. Python API: Diagnostics in result

```bash
uv run python3 -c "
import asyncio
from cellos_acp import AcpClient

async def main():
    result = await AcpClient(agent='opencode').run('Say hi')
    assert result.success
    assert result.session_id is not None
    assert result.message_id is not None
    assert result.started_at is not None
    assert result.completed_at is not None
    assert result.last_event_type is not None
    print(f'OK: session={result.session_id} msg={result.message_id} last_event={result.last_event_type}')

asyncio.run(main())
"
```

**Expected:** `OK: session=ses_... msg=msg_... last_event=AgentMessageChunk` — result carries session ID, message ID, timestamps, and last event type.

---

## 22. Python API: on_event callback

```bash
uv run python3 -c "
import asyncio
from cellos_acp import AcpClient

async def main():
    events = []

    async def on_event(event):
        events.append(event)

    result = await AcpClient(agent='opencode').run('Say hi', on_event=on_event)
    assert result.success
    assert len(events) > 0
    print(f'OK: {len(events)} events captured via callback')
    for e in events[:3]:
        print(f'  {e[\"event_type\"]} at {e[\"event_at\"]}')

asyncio.run(main())
"
```

**Expected:** `OK: N events captured via callback` — callback receives event dictionaries with `session_id`, `message_id`, `event_type`, `event_at`, and previews.

---

## 23. CLI: JSON diagnostics on success

```bash
cellos-acp run "Say hi" --json | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['success'] is True
diag = d['diagnostics']
assert diag['session_id'] is not None
assert diag['message_id'] is not None
assert diag['started_at'] is not None
assert diag['completed_at'] is not None
assert diag['last_event_type'] is not None
assert diag['timeout'] is False
assert diag['aborted'] is False
assert diag['active_tool_calls'] == []
print('OK: diagnostics present in JSON output')
"
```

**Expected:** `OK: diagnostics present in JSON output` — CLI JSON output includes diagnostics block with session/message IDs, timestamps, last event, and tool call state.

---

## 24. Python API: Structured result capture

```bash
uv run python3 -c "
from cellos_acp.client import _EventCollector
from acp.schema import ToolCallStart, ToolCallProgress

collector = _EventCollector()
collector.set_required_output_tool('cellos_submit_reply')
collector.on_tool_start(
    ToolCallStart(
        tool_call_id='tc_structured',
        title='cellos_submit_reply',
        raw_input={'summary': 'done', 'success': True},
        session_update='tool_call',
    )
)
collector.on_tool_progress(
    ToolCallProgress(
        tool_call_id='tc_structured',
        title='cellos_submit_reply',
        status='completed',
        raw_output={'summary': 'done', 'success': True},
        session_update='tool_call_update',
    )
)
result = collector.to_result()
assert result.structured_result is not None
assert result.structured_result.data['summary'] == 'done'
print('OK: structured result captured')
"
```

**Expected:** `OK: structured result captured` — verifies structured-result capture without requiring a live agent.

---

## Summary

| # | Test | Type | Live Agent? |
|---|------|------|-------------|
| 1 | List adapters | CLI | no |
| 2 | Simple prompt | CLI | yes |
| 3 | JSON output + diagnostics | CLI | yes |
| 4 | Custom command | CLI | yes |
| 5 | Timeout (partial state) | CLI | yes |
| 6 | No auto-approve | CLI | yes |
| 7 | Import + run | API | yes |
| 8 | combined_text fallback | API | yes |
| 9 | Timeout (partial state) | API | yes |
| 10 | Registry | Unit | no |
| 11 | Result dataclass + diagnostics | Unit | no |
| 12 | text_wait=0 | API | yes |
| 13 | --text-wait=0 | CLI | yes |
| 14 | --cwd option | CLI | yes |
| 15 | env parameter | Unit | no |
| 16 | Unknown agent error | API | no |
| 17 | Binary missing error | CLI | no |
| 18 | Tool call collection + active | API | yes |
| 19 | Debug log file | CLI | yes |
| 20 | Logging configuration | API | yes |
| 21 | Diagnostics in result | API | yes |
| 22 | on_event callback | API | yes |
| 23 | JSON diagnostics on success | CLI | yes |
| 24 | Structured result capture | API | no |
