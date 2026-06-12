"""End-to-end tests for cellos-acp against real agents.

These tests require the agent binaries to be installed and configured.
Run with: pytest tests/test_e2e.py -v --timeout=30
"""

import asyncio
import json
import os
import pytest
import subprocess
import sys
from pathlib import Path


@pytest.fixture
def log_file(tmp_path):
    return str(tmp_path / "test-cellos-acp.log")


@pytest.fixture(scope="session")
def opencode_installed():
    """Check if opencode is available."""
    try:
        result = subprocess.run(
            ["opencode", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class TestE2EOpencode:
    """E2E tests against opencode agent."""

    @pytest.mark.skipif(
        not opencode_installed,
        reason="opencode not installed",
    )
    def test_basic_prompt(self):
        """Agent responds to a basic prompt with expected text."""
        from cellos_acp import AcpClient

        async def run():
            client = AcpClient(
                agent="opencode",
                cwd=str(Path.cwd()),
            )
            result = await client.run("Respond with exactly: SMOKE_TEST_OK")
            assert result.success
            assert "SMOKE_TEST_OK" in result.combined_text

        asyncio.run(run())

    @pytest.mark.skipif(
        not opencode_installed,
        reason="opencode not installed",
    )
    def test_text_and_thinking_separated(self):
        """Test that text and thinking are properly separated."""
        from cellos_acp import AcpClient

        async def run():
            client = AcpClient(
                agent="opencode",
                cwd=str(Path.cwd()),
            )
            result = await client.run("What is 2+2? Answer with just the number.")
            assert result.success
            assert "4" in result.combined_text

        asyncio.run(run())

    @pytest.mark.skipif(
        not opencode_installed,
        reason="opencode not installed",
    )
    def test_json_output_format(self):
        """Test JSON output format via CLI."""
        result = subprocess.run(
            [sys.executable, "-m", "cellos_acp", "run", "--agent", "opencode", "--json", "Say hello"],
            capture_output=True,
            text=True,
            timeout=360,
            cwd=str(Path.cwd()),
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "text" in output
        assert "thinking" in output
        assert "tool_calls" in output
        assert "stop_reason" in output
        assert "success" in output
        assert output["success"] is True

    @pytest.mark.skipif(
        not opencode_installed,
        reason="opencode not installed",
    )
    def test_text_output_format(self):
        """Test text output format via CLI."""
        result = subprocess.run(
            [sys.executable, "-m", "cellos_acp", "run", "--agent", "opencode", "--text", "Say hello"],
            capture_output=True,
            text=True,
            timeout=360,
            cwd=str(Path.cwd()),
        )
        assert result.returncode == 0
        assert not result.stdout.strip().startswith("{")
        assert len(result.stdout.strip()) > 0

    @pytest.mark.skipif(
        not opencode_installed,
        reason="opencode not installed",
    )
    def test_custom_command(self):
        """Test custom command override."""
        from cellos_acp import AcpClient

        async def run():
            client = AcpClient(
                command="opencode",
                args=["acp"],
                cwd=str(Path.cwd()),
            )
            result = await client.run("Respond with exactly: CUSTOM_CMD_OK")
            assert result.success
            assert "CUSTOM_CMD_OK" in result.combined_text

        asyncio.run(run())

    @pytest.mark.skipif(
        not opencode_installed,
        reason="opencode not installed",
    )
    def test_timeout_handling(self):
        """Test that timeout returns error result."""
        from cellos_acp import AcpClient

        async def run():
            client = AcpClient(
                agent="opencode",
                cwd=str(Path.cwd()),
                timeout=1,
            )
            result = await client.run(
                "Write a detailed 500-word essay about the history of computing"
            )
            assert result.success is False
            assert result.error is not None
            assert "timeout" in str(result.error).lower()

        asyncio.run(run())

    @pytest.mark.skipif(
        not opencode_installed,
        reason="opencode not installed",
    )
    def test_cli_list_agents(self):
        """Test CLI list command."""
        result = subprocess.run(
            [sys.executable, "-m", "cellos_acp", "list"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(Path.cwd()),
        )
        assert result.returncode == 0
        assert "opencode" in result.stdout
        assert "hermes" in result.stdout


class TestE2ERegistry:
    """E2E tests for adapter registry."""

    def test_all_adapters_have_commands(self):
        """All registered adapters have valid commands."""
        from cellos_acp.registry import _registry

        for name in _registry.list_names():
            adapter = _registry.get(name)
            assert adapter is not None
            assert adapter.command
            assert adapter.full_command()


class TestE2EClient:
    """E2E tests for client initialization."""

    def test_client_initialization(self):
        """Test client can be initialized with various parameters."""
        from cellos_acp import AcpClient

        client = AcpClient(agent="opencode")
        assert client._command == "opencode"
        assert client._args == ["acp"]

        client = AcpClient(command="custom", args=["--test"])
        assert client._command == "custom"
        assert client._args == ["--test"]

        client = AcpClient(agent="opencode", env={"TEST": "value"})
        assert client._env == {"TEST": "value"}

    def test_client_timeout(self):
        """Test timeout parameter."""
        from cellos_acp import AcpClient

        client = AcpClient(agent="opencode", timeout=30)
        assert client._timeout == 30

        client = AcpClient(agent="opencode")
        assert client._timeout == 300


class TestE2ELogging:
    """E2E tests for debug logging."""

    @pytest.mark.skipif(
        not opencode_installed,
        reason="opencode not installed",
    )
    def test_cli_log_file_contains_debug_entries(self, log_file):
        """CLI --log-file creates log file with session and event debug entries."""
        result = subprocess.run(
            [
                sys.executable, "-m", "cellos_acp", "run",
                "--agent", "opencode",
                "--log-file", log_file,
                "--text",
                "Say hi"
            ],
            capture_output=True,
            text=True,
            timeout=360,
            cwd=str(Path.cwd()),
        )
        assert result.returncode == 0
        assert os.path.exists(log_file)
        content = open(log_file).read()
        assert "DEBUG" in content
        assert "spawning" in content
        assert "session created" in content
        assert "sending prompt" in content

    def test_python_configure_logging(self, log_file):
        """Python API configure_logging() creates file handler."""
        from cellos_acp import configure_logging

        returned = configure_logging(log_file)
        assert returned == log_file
        assert os.path.exists(log_file)
        content = open(log_file).read()
        assert "cellos-acp logging configured" in content

    def test_python_api_logging_on_run(self, log_file):
        """Python API run with logging captures debug entries."""
        import asyncio
        from cellos_acp import configure_logging, AcpClient

        configure_logging(log_file)

        async def run():
            return await AcpClient(
                agent="opencode",
                cwd=str(Path.cwd()),
            ).run("Say hi")

        if opencode_installed:
            result = asyncio.run(run())
            assert result.success
            content = open(log_file).read()
            assert "AcpClient init" in content
            assert "spawning" in content
        else:
            pytest.skip("opencode not installed")

    def test_logging_truncation_marker(self, log_file):
        """Long content is truncated with [TRUNCATED] marker."""
        from cellos_acp.client import _debug_truncate

        long_text = "x" * 1000
        truncated = _debug_truncate(long_text)
        assert "[TRUNCATED: 1000 chars total]" in truncated
        assert len(truncated.split("[TRUNCATED")[0]) < 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=30"])
