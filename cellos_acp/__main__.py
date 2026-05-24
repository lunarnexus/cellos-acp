"""CLI entry point for cellos-acp testing."""

from __future__ import annotations

import asyncio
import json
import sys

import click

from .client import AcpClient
from .registry import _registry


@click.group()
def cli():
    """cellos-acp — lightweight ACP client tester."""
    pass


@cli.command()
@click.argument("prompt")
@click.option("--agent", "-a", default="opencode", help="Agent name (default: opencode)")
@click.option("--custom-cmd", help="Custom command instead of registered adapter")
@click.option("--custom-args", multiple=True, help="Custom args (repeatable)")
@click.option("--cwd", default=".", help="Working directory")
@click.option("--timeout", type=float, default=120, help="Timeout in seconds")
@click.option("--no-approve", is_flag=True, help="Don't auto-approve permissions")
@click.option("--json", "json_output", is_flag=True, help="Output result as JSON")
@click.option("--quiet", is_flag=True, help="Only print combined text")
def run(
    prompt, agent, custom_cmd, custom_args, cwd, timeout, no_approve, json_output, quiet
):
    """Run a prompt against an ACP agent."""

    client = AcpClient(
        agent=agent,
        command=custom_cmd,
        args=list(custom_args) if custom_args else None,
        cwd=cwd,
        auto_approve=not no_approve,
        timeout=timeout,
    )

    result = asyncio.run(client.run(prompt))

    if json_output:
        click.echo(json.dumps(_result_to_dict(result), indent=2))
    elif quiet:
        click.echo(result.combined_text)
    else:
        if result.error:
            click.echo(f"ERROR: {result.error}", err=True)
            sys.exit(1)
        click.echo(f"--- text ({len(result.text)} chars) ---")
        click.echo(result.text or "(empty)")
        if result.thinking:
            click.echo(f"\n--- thinking ({len(result.thinking)} chars) ---")
            click.echo(result.thinking)
        if result.tool_calls:
            click.echo(f"\n--- tool calls ({len(result.tool_calls)}) ---")
            for tc in result.tool_calls:
                click.echo(f"  [{tc.status}] {tc.title}")
        click.echo(f"\n--- stop: {result.stop_reason} ---")


@cli.command("list")
def list_agents():
    """List available agent adapters."""
    for name in _registry.list_names():
        adapter = _registry.get(name)
        cmd = " ".join(adapter.full_command())
        quirks = ", ".join(f"{k}={v}" for k, v in adapter.quirks.items()) or "(none)"
        click.echo(f"  {name:12s}  {cmd:40s}  {quirks}")


def _result_to_dict(result) -> dict:
    return {
        "text": result.text,
        "thinking": result.thinking,
        "tool_calls": [
            {
                "id": tc.tool_call_id,
                "title": tc.title,
                "status": tc.status,
            }
            for tc in result.tool_calls
        ],
        "stop_reason": result.stop_reason,
        "error": str(result.error) if result.error else None,
        "success": result.success,
    }


if __name__ == "__main__":
    cli()
