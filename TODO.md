# cellos-acp TODO

## Model selection

Opencode doesn't accept `--model` as a CLI flag. Model is set via config.

**Best option:** `OPENCODE_CONFIG_CONTENT` env var — runtime JSON config override.

```bash
OPENCODE_CONFIG_CONTENT='{"model":"lmstudio/qwen3.6-35b-a3b-mtp"}' opencode acp
```

**Implementation:** Add `model` parameter to `AcpClient` that translates to:

```python
env={"OPENCODE_CONFIG_CONTENT": json.dumps({"model": model})}
```

**Other options found:**
- `{env:OPENCODE_MODEL}` in config (requires static config change)
- `OPENCODE_CONFIG` env var (points to custom config file)
- Per-agent model in `opencode.json` (static, not runtime)

**Sources:**
- https://opencode.ai/docs/config/ (env vars, inline config)
- https://opencode.ai/docs/agents/ (per-agent model override)
