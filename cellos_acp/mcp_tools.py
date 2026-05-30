"""Ephemeral MCP server helpers for structured output tools."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from typing import Any

from acp.schema import McpServerStdio


CELLOS_MCP_SERVER = "cellos-result-tools"


@dataclass
class _McpServerProcess:
    """Manages a spawned ephemeral MCP server subprocess."""

    proc: subprocess.Popen[str]
    mcp_server: McpServerStdio


def _build_mcp_script(tool_schemas: list[dict[str, Any]]) -> str:
    tools_json = json.dumps(tool_schemas)
    return textwrap.dedent(
        f"""
        from __future__ import annotations

        import asyncio
        import json
        from typing import Any

        from fastmcp import FastMCP
        from fastmcp.tools.function_tool import Tool

        CELLOS_MCP_SERVER = "cellos-result-tools"
        TOOL_DEFS = json.loads({tools_json!r})

        def _python_type(schema: dict[str, Any]) -> str:
            match schema.get("type"):
                case "string":
                    return "str"
                case "integer":
                    return "int"
                case "number":
                    return "float"
                case "boolean":
                    return "bool"
                case "array":
                    return "list[Any]"
                case "object":
                    return "dict[str, Any]"
                case _:
                    return "Any"

        def _build_function_source(index: int, tool_def: dict[str, Any]) -> str:
            params = tool_def.get("parameters", {{}})
            properties = params.get("properties", {{}})
            required = set(params.get("required", []))

            parts = []
            for name, schema in properties.items():
                py_type = _python_type(schema)
                if name in required:
                    parts.append(f"{{name}}: {{py_type}}")
                else:
                    parts.append(f"{{name}}: {{py_type}} | None = None")

            signature = ", ".join(parts)
            payload_lines = ["    payload = {{"]
            for name in properties:
                payload_lines.append(f"        {{name!r}}: {{name}},")
            payload_lines.append("    }}")
            payload_lines.append('    return {{"result": payload}}')

            body = "\\n".join(payload_lines)
            return f"def tool_{{index}}({{signature}}):\\n{{body}}"

        mcp = FastMCP(CELLOS_MCP_SERVER)

        for index, tool_def in enumerate(TOOL_DEFS):
            namespace = {{"Any": Any}}
            source = _build_function_source(index, tool_def)
            exec(source, namespace)
            fn = namespace[f"tool_{{index}}"]
            tool = Tool.from_function(
                fn,
                name=tool_def["name"],
                description=tool_def.get("description"),
            )
            mcp.add_tool(tool)


        async def main() -> None:
            await mcp.run_stdio_async(show_banner=False)


        asyncio.run(main())
        """
    )


def spawn_mcp_server(
    tool_schemas: list[dict[str, Any]],
    server_name: str = CELLOS_MCP_SERVER,
) -> _McpServerProcess:
    script = _build_mcp_script(tool_schemas)
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return _McpServerProcess(
        proc=proc,
        mcp_server=McpServerStdio(
            command=sys.executable,
            args=["-c", script],
            env=[],
            name=server_name,
        ),
    )
