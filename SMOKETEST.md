# cellos-acp Smoke Tests

Run each step sequentially. Verify the **Expected** output before proceeding.

All tests use `opencode` (default agent). Steps 1-6 are CLI. Steps 7-11 are Python API (run from project dir with `uv run`).

## Prerequisites

```bash
which cellos-acp && which opencode
```

**Expected:** Both return paths.

---

## 1. CLI: List adapters

```bash
cellos-acp list
```

**Expected:** 6 agents listed. opencode shows `thought_only=True`.

---

## 2. CLI: Simple prompt

```bash
cellos-acp run "Say hello in three words" --quiet
```

**Expected:** A short greeting, no headers.

---

## 3. CLI: JSON output

```bash
cellos-acp run "Reply with the number four" --json
```

**Expected:** Valid JSON with `success: true` and `text` containing "4".

---

## 4. CLI: Custom command (bypass registry)

```bash
cellos-acp run "Say hi" --custom-cmd opencode --custom-args acp --timeout 60 --quiet
```

**Expected:** A greeting.

---

## 5. CLI: Timeout

```bash
cellos-acp run "Write a very long essay" --timeout 2 --json
```

**Expected:** JSON with `success: false` and `error` containing "timeout".

---

## 6. CLI: No auto-approve

```bash
cellos-acp run "Say something brief" --no-approve --quiet
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

## 8. Python API: Thought-only mode (opencode quirk)

```bash
uv run python3 -c "
import asyncio
from cellos_acp import AcpClient

async def main():
    result = await AcpClient(agent='opencode').run('Name a fruit')
    assert result.text, 'text should not be empty'
    print(f'OK: {repr(result.text[:50])}')

asyncio.run(main())
"
```

**Expected:** `text` populated (promoted from thinking).

---

## 9. Python API: Timeout

```bash
uv run python3 -c "
import asyncio
from cellos_acp import AcpClient

async def main():
    result = await AcpClient(agent='opencode', timeout=1, quiet_wait=0).run('Write a very long response')
    assert not result.success
    print('OK: timeout handled')

asyncio.run(main())
"
```

**Expected:** `OK: timeout handled`

---

## 10. Registry: Get adapter

```bash
uv run python3 -c "
from cellos_acp import get_adapter, AgentRegistry

adapter = get_adapter('opencode')
assert adapter.command == 'opencode' and adapter.quirks.get('thought_only')
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
print('OK: result tests passed')
"
```

**Expected:** `OK: result tests passed`

---

## Summary

| # | Test | Type | Live Agent? |
|---|------|------|-------------|
| 1 | List adapters | CLI | no |
| 2 | Simple prompt | CLI | yes |
| 3 | JSON output | CLI | yes |
| 4 | Custom command | CLI | yes |
| 5 | Timeout | CLI | yes |
| 6 | No auto-approve | CLI | yes |
| 7 | Import + run | API | yes |
| 8 | Thought-only | API | yes |
| 9 | Timeout | API | yes |
| 10 | Registry | Unit | no |
| 11 | Result dataclass | Unit | no |
