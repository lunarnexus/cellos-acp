"""Agent adapter base and registry."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class AgentAdapter:
    """Configuration for a single ACP agent adapter.

    Attributes:
        name: Human-friendly name (e.g. "opencode").
        command: Executable to spawn.
        args: Arguments passed to the executable (e.g. ["acp"]).
        env: Extra environment variables (merged with os.environ).
    """

    name: str
    command: str
    args: list[str] = dataclasses.field(default_factory=list)
    env: dict[str, str] = dataclasses.field(default_factory=dict)

    def full_command(self) -> list[str]:
        return [self.command, *self.args]


# ── Built-in adapters ──────────────────────────────────────────────

ADAPTERS: dict[str, AgentAdapter] = {
    "opencode": AgentAdapter(
        name="opencode",
        command="opencode",
        args=["acp"],
    ),
    "openclaw": AgentAdapter(
        name="openclaw",
        command="acpx",
        args=["openclaw", "exec"],
    ),
    "hermes": AgentAdapter(
        name="hermes",
        command="hermes",
        args=["acp"],
    ),
    "pi": AgentAdapter(
        name="pi",
        command="pi",
        args=["acp"],
    ),
    "claude": AgentAdapter(
        name="claude",
        command="claude",
        args=["--experimental-acp"],
    ),
    "codex": AgentAdapter(
        name="codex",
        command="codex",
        args=["--acp"],
    ),
}


class AgentRegistry:
    """Registry of agent adapters."""

    def __init__(self):
        self._adapters = dict(ADAPTERS)

    def get(self, name: str) -> AgentAdapter | None:
        return self._adapters.get(name)

    def register(self, adapter: AgentAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def list_names(self) -> list[str]:
        return sorted(self._adapters.keys())


_registry = AgentRegistry()


def get_adapter(name: str) -> AgentAdapter:
    """Get an adapter by name. Raises KeyError if not found."""
    adapter = _registry.get(name)
    if adapter is None:
        raise KeyError(
            f"Unknown agent '{name}'. Available: {_registry.list_names()}"
        )
    return adapter
