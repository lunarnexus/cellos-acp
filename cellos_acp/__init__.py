"""cellos-acp — lightweight ACP client with multi-agent adapters."""

from .result import AcpRunResult, ToolCallRecord
from .client import AcpClient
from .registry import AgentAdapter, AgentRegistry, get_adapter

__all__ = ["AcpClient", "AcpRunResult", "ToolCallRecord", "AgentAdapter", "AgentRegistry", "get_adapter"]
