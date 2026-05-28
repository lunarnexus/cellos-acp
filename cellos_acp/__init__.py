"""cellos-acp — lightweight ACP client with multi-agent adapters."""

import logging
from datetime import datetime, timezone

from .result import AcpRunResult, ToolCallRecord
from .client import AcpClient
from .registry import AgentAdapter, AgentRegistry, get_adapter

__all__ = [
    "AcpClient",
    "AcpRunResult",
    "ToolCallRecord",
    "AgentAdapter",
    "AgentRegistry",
    "get_adapter",
    "configure_logging",
]

DEFAULT_LOG_FILE = "/tmp/cellos-acp.log"
LOG_FORMAT = "%(asctime)s [%(levelname)-5s] %(name)s:%(lineno)d - %(message)s"


def configure_logging(log_file: str | None = None) -> str:
    """Configure file-based logging for cellos-acp.

    Sets up a FileHandler on the root logger that writes DEBUG+ messages
    to a log file.  Does NOT affect stdout or stderr.

    Args:
        log_file: Path to log file.  Defaults to /tmp/cellos-acp.log.

    Returns:
        The path to the log file.
    """
    path = log_file or DEFAULT_LOG_FILE
    handler = logging.FileHandler(path)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root = logging.getLogger()
    if root.level > logging.DEBUG:
        root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    logging.debug("cellos-acp logging configured -> %s", path)
    return path
