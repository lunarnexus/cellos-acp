# cellos-acp TODO

## 1. Model selection via `--model` flag

Opencode doesn't accept `--model` as a CLI flag — model is set via config. Use `OPENCODE_CONFIG_CONTENT` env var to override at runtime.

**What:** Add `model` parameter to `AcpClient` → translates to `OPENCODE_CONFIG_CONTENT` env var.

**Why:** Caller should be able to specify model without touching config files.

## 2. Approval callback mechanism

`--no-approve` currently just cancels all permission requests. No way for the caller to decide.

**What:** Add `on_permission` callback to `AcpClient.run()` that receives the permission request and returns the outcome.

**Why:** Calling apps need to approve/deny tool actions (file edits, commands) instead of blindly auto-approving or cancelling.

## 3. Dynamic MCP idea.  

Investigate.  Currently we use MCP for a "LLM fills out a form like an office worker would" style of call/callback.  This is much better than simply asking the LLM to "output your answer in X format".  I want to explore this idea more.  The calling app can submit a schema each time a question is asked specifying the output format it wants back.  Let's check what we have now, then investigate options, see if there are existig techniques/tools that do this, then see how it could work in our app(s) (cellos and cellos-acp).
