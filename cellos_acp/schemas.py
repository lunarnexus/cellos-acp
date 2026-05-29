"""Default JSON schemas for structured output tools."""

from __future__ import annotations

from typing import Any


def _schema(
    tool_name: str,
    description: str,
    properties: dict[str, dict[str, Any]],
    required: list[str],
) -> dict[str, Any]:
    return {
        "name": tool_name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def make_prompt_schema(
    tool_name: str = "cellos_submit_prompt",
    description: str = (
        "Submit the final planning prompt. Call exactly once when planning is complete."
    ),
) -> dict[str, Any]:
    return _schema(
        tool_name,
        description,
        {
            "objective": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
            "approach": {"type": "string"},
            "verification": {"type": "array", "items": {"type": "string"}},
            "dependencies": {"type": "array", "items": {"type": "string"}},
            "risks": {"type": "array", "items": {"type": "string"}},
            "child_tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "role": {"type": "string"},
                        "task_type": {"type": "string"},
                        "details": {"type": "string"},
                        "success_criteria": {"type": "string"},
                        "failure_criteria": {"type": "string"},
                        "dependencies": {"type": "array", "items": {"type": "string"}},
                        "blocks_parent": {"type": "boolean"},
                    },
                    "required": ["title"],
                },
            },
        },
        ["objective", "steps"],
    )


def make_reply_schema(
    tool_name: str = "cellos_submit_reply",
    description: str = (
        "Submit the final execution reply. Call exactly once when execution is complete or blocked."
    ),
) -> dict[str, Any]:
    return _schema(
        tool_name,
        description,
        {
            "summary": {"type": "string"},
            "success": {"type": "boolean"},
            "actions_taken": {"type": "array", "items": {"type": "string"}},
            "files_changed": {"type": "array", "items": {"type": "string"}},
            "commands_run": {"type": "array", "items": {"type": "string"}},
            "criteria_met": {"type": "array", "items": {"type": "string"}},
            "issues": {"type": "array", "items": {"type": "string"}},
        },
        ["summary", "success"],
    )


def make_blocker_schema(
    tool_name: str = "cellos_report_blocker",
    description: str = "Report that the task cannot proceed without human input.",
) -> dict[str, Any]:
    return _schema(
        tool_name,
        description,
        {
            "reason": {"type": "string"},
            "needed_from_human": {"type": "string"},
            "partial_progress": {"type": "array", "items": {"type": "string"}},
        },
        ["reason", "needed_from_human"],
    )


def schema_for_tool_name(tool_name: str) -> dict[str, Any]:
    if tool_name == "cellos_submit_prompt":
        return make_prompt_schema(tool_name)
    if tool_name == "cellos_submit_reply":
        return make_reply_schema(tool_name)
    if tool_name == "cellos_report_blocker":
        return make_blocker_schema(tool_name)
    return {
        "name": tool_name,
        "description": f"Submit structured output for {tool_name}.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    }
