# Research: CelloS ACP Gap Analysis

**Date:** 2026-06-10
**Purpose:** Compare cellos-acp against the acpx reference implementation and ACP protocol specification to identify missing features and prioritize work.

---

## 1. Sources Analyzed

| Source | Location | Description |
|--------|----------|-------------|
| **cellos-acp** | `../cellos-acp/` | Python ACP client library (current implementation) |
| **acpx** | `../acpx/` | TypeScript reference implementation by Zed/Anthropic |
| **ACP Protocol Spec** | https://agentclientprotocol.com | Official Agent Client Protocol v1 specification |

---

## 2. acpx Architecture Summary

acpx is a production-grade ACP client runtime with the following major subsystems:

### Core Protocol Layer (`src/acp/`)
- Full JSON-RPC 2.0 stdio transport
- Initialize, authenticate, session lifecycle (new/load/close/delete)
- Terminal manager with process group tracking and cross-platform kill support
- Error normalization and typed error shapes
- Model support detection

### Runtime Engine (`src/runtime/engine/`)
- `AcpRuntimeManager` - Central orchestrator for sessions and turns
- Session reuse policy for reconnecting to existing agents
- Reconnect support with state replay (mode, model, config options)
- Prompt turn execution with timeout control and idle drain

### Flow Engine (`src/flows/`)
- DAG-based orchestration: `acp` nodes (AI prompts), `compute` nodes (code), `action` nodes (shell/function), `checkpoint` nodes
- Decision routing for conditional branching
- Switch edges based on JSONPath expressions
- Store system for managing reusable flow definitions

### Session Management (`src/session/`)
- File-based session store with CRUD operations
- Import/export support (JSON format)
- Conversation model tracking
- Live checkpoints and persistence layer
- Mode preference management

### CLI Framework (`src/cli/`)
- Commands: run, status, config, list sessions
- Queue/IPC system for multi-process turn ownership
- JSON output formatting with structured renderers
- Permission prompts in interactive mode

### Other Features
- Agent registry resolution
- MCP server spawn and connect
- Permission policies (allow/auto/interactive modes)
- Performance metrics capture

---

## 3. cellos-acp Current Implementation Summary

cellos-acp is a lightweight Python ACP client with these capabilities:

| Component | Description |
|-----------|-------------|
| **`AcpClient`** | Spawn agent subprocess via stdio, initialize protocol, create session, send prompt, collect events into `AcpRunResult` |
| **`_EventCollector`** | Collects AgentMessageChunk, AgentThoughtChunk, ToolCallStart, ToolCallProgress |
| **Adapter Registry** | Pre-configured adapters for opencode and hermes agents |
| **MCP Tools** | Spawn MCP servers as subprocesses, expose tools to agents via stdio |
| **Permission Handling** | Auto-approve mode (selects first "allow" option) |
| **Text Idle Detection** | Wait strategy: return after N seconds of no streaming updates |
| **Structured Results** | Capture structured output from designated MCP tool calls |

---

## 4. ACP Protocol v1 - Required Methods

### Agent Methods (Client -> Agent)

| Method | Status | Description |
|--------|--------|-------------|
| `initialize` | ✅ Baseline | Negotiate versions and exchange capabilities |
| `authenticate` | ⚠️ Optional | Authenticate with the agent if required |
| `session/new` | ✅ Baseline | Create a new conversation session |
| `session/load` | ⚠️ Optional | Load an existing session (requires `loadSession` capability) |
| `session/prompt` | ✅ Baseline | Send user prompts to the agent |
| `session/set_mode` | ⚠️ Optional | Switch between agent operating modes |
| `logout` | ⚠️ Optional | End current authenticated state |

### Client Methods (Agent -> Client)

| Method | Status | Description |
|--------|--------|-------------|
| `session/request_permission` | ✅ Baseline | Request user authorization for tool calls |
| `fs/read_text_file` | ⚠️ Optional | Read file contents |
| `fs/write_text_file` | ⚠️ Optional | Write file contents |
| `terminal/*` | ⚠️ Optional | Terminal lifecycle (create/output/release/wait_for_exit/kill) |

### Notifications

| Notification | Description |
|--------------|-------------|
| `session/update` | Agent sends progress updates (message chunks, tool calls, plans, mode changes) |
| `session/cancel` | Client cancels ongoing operations |

---

## 5. Gap Analysis

### Priority 1: Core Protocol Completeness

| # | Missing Feature | acpx Reference | ACP Spec Section | Effort |
|---|----------------|----------------|------------------|--------|
| 1 | **Session Resume** (`session/load`) | `src/acp/client.ts` lines ~300-400 | Session Setup > Loading Sessions | Medium |
| 2 | **Session Close** (`session/close`) | Runtime manager | Session Close (stabilized) | Small |
| 3 | **Session Delete** (`session/delete`) | `src/acp/client.ts` | Session Delete (stabilized) | Small |
| 4 | **Authentication** (`authenticate`) | `src/acp/auth-env.ts` + client | Authentication | Medium |
| 5 | **Session Modes** (`session/set_mode`) | Runtime manager | Session Modes | Medium |
| 6 | **Config Options** (model, system prompt) | `src/session/config-options.ts` | Session Config Options | Medium |

### Priority 2: Runtime Features

| # | Missing Feature | acpx Reference | Effort |
|---|----------------|----------------|--------|
| 7 | **Terminal Support** | `src/acp/terminal-manager.ts` | Large |
| 8 | **Session Persistence** (file store) | `src/session/persistence/` | Medium |
| 9 | **Reconnect/Reuse** | `src/runtime/engine/reuse-policy.ts`, `reconnect.ts` | Large |
| 10 | **File System Methods** | Client capabilities negotiation | Small |

### Priority 3: CLI & Observability

| # | Missing Feature | acpx Reference | Effort |
|---|----------------|----------------|--------|
| 11 | **CLI Commands** (status, list sessions) | `src/cli/` | Medium |
| 12 | **Queue/IPC Turn Ownership** | `src/cli/queue/` | Large |
| 13 | **Agent Registry Resolution** | `src/agent-registry.ts` | Small |

### Priority 4: Advanced Features

| # | Missing Feature | acpx Reference | Effort |
|---|----------------|----------------|--------|
| 14 | **Flow Engine** (DAG orchestration) | `src/flows/` | XLarge |
| 15 | **Session Export/Import** | `src/session/export.ts`, `import.ts` | Medium |

---

## 6. Key Architecture Differences

| Aspect | cellos-acp | acpx |
|--------|-----------|------|
| Language | Python | TypeScript |
| Design | Simple async client, single-shot prompts | Full runtime with session lifecycle management |
| Session Model | Ephemeral (new per run) | Persistent with resume/reconnect support |
| Event Model | Collect-then-return pattern | Streaming event queue with turn tasks |
| Orchestration | None (single prompt) | DAG-based flow engine |
| CLI | None (library only) | Full CLI with IPC queue system |

---

## 7. Recommendations

1. **Start with Protocol Completeness** - Implement session resume, close, and modes to match ACP v1 baseline expectations
2. **Add Session Persistence** - File-based store enables all lifecycle features and is foundational for reconnect/reuse
3. **Keep it Lightweight** - cellos-acp doesn't need the full flow engine or IPC queue; focus on what CelloS needs as a consumer
4. **Follow acpx Patterns** - Use acpx's error handling, permission decisions, and session state management as reference patterns