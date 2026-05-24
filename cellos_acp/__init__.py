"""cellos-acp — lightweight ACP client with multi-agent adapters."""

from .result import AcpRunResult
from .client import AcpClient
from .registry import AgentRegistry, get_adapter

__all__ = ["AcpClient", "AcpRunResult", "AgentRegistry", "get_adapter"]
