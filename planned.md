# Plan: CelloS ACP Enhancement Roadmap

**Date:** 2026-06-10
**Based on:** `research.md` gap analysis

---

## Strategy

cellos-acp will remain a **lightweight Python library**. We won't replicate acpx's full runtime (flow engine, IPC queue system). Instead, we'll focus on:

1. Protocol completeness for ACP v1 compliance
2. Session persistence to enable lifecycle features
3. Practical enhancements that CelloS tasks actually need

---

## Phase 1: Core Protocol Completeness

**Goal:** Support all stabilized ACP v1 methods.

### Task 1.1: Session Close (`session/close`)
- **What:** Add `close_session` method to the connection client
- **Reference:** acpx `src/runtime/engine/manager.ts`, ACP spec "Session Close"
- **Changes:** 
  - Add `close_session` in `cellos_acp/client.py` (spawn_agent_process)
  - Call close before process exit in the run lifecycle
- **Effort:** Small

### Task 1.2: Session Resume (`session/load`)
- **What:** Support loading existing sessions by ID
- **Reference:** acpx `src/acp/client.ts`, ACP spec "Session Setup > Loading Sessions"
- **Changes:**
  - Add `load_session` method to connection client
  - Extend `AcpClient.run()` with optional `session_id` parameter
  - If `session_id` provided, attempt load before create
- **Effort:** Medium

### Task 1.3: Session Delete (`session/delete`)
- **What:** Support deleting sessions on the agent
- **Reference:** acpx `src/acp/client.ts`, ACP spec "Session Delete"
- **Changes:**
  - Add `delete_session` method to connection client
- **Effort:** Small

### Task 1.4: Authentication (`authenticate`)
- **What:** Support auth credentials during initialization
- **Reference:** acpx `src/acp/auth-env.ts`, ACP spec "Authentication"
- **Changes:**
  - Add `auth_credentials` parameter to `AcpClient.__init__`
  - Send authenticate call after initialize if credentials provided
- **Effort:** Medium

### Task 1.5: Session Modes (`session/set_mode`)
- **What:** Support switching agent modes (plan/act/edit)
- **Reference:** acpx runtime manager, ACP spec "Session Modes"
- **Changes:**
  - Add `set_session_mode` method to connection client
  - Add `mode` parameter to `AcpClient.run()`
  - Set mode after session creation before prompt
- **Effort:** Medium

### Task 1.6: Config Options (model, system prompt)
- **What:** Support model selection and system prompts at session level
- **Reference:** acpx `src/session/config-options.ts`, ACP spec "Session Config Options"
- **Changes:**
  - Add `system_prompt` parameter to `AcpClient.__init__`
  - Pass config options during `session/new` creation (already partially supported via `OPENCODE_CONFIG_CONTENT`)
  - Add `set_session_config_option` method for runtime changes
- **Effort:** Medium

---

## Phase 2: Session Persistence

**Goal:** Store session metadata on disk so sessions can be resumed, listed, and tracked.

### Task 2.1: Session Record Schema
- **What:** Define Python dataclasses for session records
- **Reference:** acpx `src/types.ts` SessionRecord type
- **Changes:**
  - New file: `cellos_acp/session_store.py`
  - Dataclasses: `SessionRecord`, `SessionState`
- **Effort:** Small

### Task 2.2: File-Based Session Store
- **What:** CRUD operations for session records on disk (JSON files)
- **Reference:** acpx `src/runtime/public/file-session-store.ts`, `src/session/persistence/`
- **Changes:**
  - Implement: `create_session_record()`, `load_session_record()`, `update_session_record()`, `list_session_records()`, `delete_session_record()`
  - Directory structure: `{state_dir}/{agent}/{session_name}.json`
- **Effort:** Medium

### Task 2.3: Integration with AcpClient
- **What:** Auto-save session records after successful runs
- **Changes:**
  - Add `state_dir` parameter to `AcpClient.__init__`
  - After run completes, persist session ID, agent, timestamps, result summary
- **Effort:** Small

### Task 2.4: Session Export/Import
- **What:** Export full session history (ACP messages) as JSON bundle
- **Reference:** acpx `src/session/export.ts`, `import.ts`
- **Changes:**
  - Add `export_session()` function that collects ACP message history
  - Add `import_session()` to restore from exported bundle
- **Effort:** Medium

---

## Phase 3: Runtime Features

**Goal:** Support terminal operations and file system methods.

### Task 3.1: Terminal Support
- **What:** Create terminals, read output, release/kill processes
- **Reference:** acpx `src/acp/terminal-manager.ts` (96 symbols)
- **Changes:**
  - New file: `cellos_acp/terminal.py`
  - Implement: `create_terminal()`, `read_output()`, `release_terminal()`, `wait_for_exit()`, `kill_terminal()`
  - Enable terminal capability during initialize
- **Effort:** Large

### Task 3.2: File System Methods
- **What:** Read/write text files via ACP protocol
- **Reference:** acpx client capabilities, ACP spec "File System"
- **Changes:**
  - Add `fs/read_text_file` and `fs/write_text_file` methods to connection client
  - Enable fs capability during initialize
- **Effort:** Small

### Task 3.3: Reconnect/Reuse Policy
- **What:** Detect if agent is still running and reuse instead of spawning new process
- **Reference:** acpx `src/runtime/engine/reuse-policy.ts`, `reconnect.ts`
- **Changes:**
  - Add session reuse logic to runtime manager
  - Track active sessions by ID, attempt reconnect before spawn
- **Effort:** Large

---

## Phase 4: CLI & Observability (Optional)

**Goal:** Provide a CLI for managing sessions and inspecting state.

### Task 4.1: CLI Commands
- **What:** `cellos-acp status`, `cellos-acp list-sessions`, `cellos-acp delete-session`
- **Changes:**
  - Extend `__main__.py` with subcommand dispatch
  - Use session store for listing/deleting
- **Effort:** Medium

### Task 4.2: Agent Registry Resolution
- **What:** Resolve agent commands from ACP registry instead of hardcoded adapters
- **Reference:** acpx `src/agent-registry.ts`
- **Changes:**
  - New file: `cellos_acp/agent_registry.py`
  - Fetch and cache agent configurations from registry API
- **Effort:** Small

---

## Phase 5: Flow Engine (Stretch)

**Goal:** DAG-based orchestration for multi-step workflows.

### Task 5.1: Flow Definition Schema
- Define node types: `acp`, `compute`, `action` (shell), `checkpoint`
- Implement edge routing with switch/conditional support

### Task 5.2: Flow Runtime
- Execute flows as DAGs, passing context between nodes
- Support session sharing across nodes in a flow

---

## Execution Order

```
Phase 1 (Protocol) -> Phase 2 (Persistence) -> Phase 3 (Runtime) -> Phase 4 (CLI) -> Phase 5 (Flow)
     Task 1.1                                            Task 2.1
     Task 1.3                                            Task 2.2
     Task 1.2                                            Task 2.3
     Task 1.4                                            Task 2.4
     Task 1.5
     Task 1.6
```

Within Phase 1, Tasks 1.1 and 1.3 are independent and can be done in parallel with 1.2-1.6 sequentially.

---

## Success Criteria per Phase

| Phase | Criterion |
|-------|-----------|
| 1 | `AcpClient` supports all stabilized ACP v1 methods; passes conformance-style smoke tests |
| 2 | Sessions persist to disk and can be resumed across process restarts |
| 3 | Terminals work for interactive commands; file reads/writes succeed |
| 4 | CLI can list, inspect, and delete sessions |
| 5 | Multi-node flows execute correctly with branching logic |