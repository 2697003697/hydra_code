"""
Command execution tools.
"""

import asyncio
import platform
from typing import Any

from ..clients.base import ToolDefinition
from .base import Tool, ToolResult


class RunCommandTool(Tool):
    name = "run_command"
    description = "Execute a shell command and return the output. Use this to run terminal commands."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to execute.",
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        command = arguments.get("command", "")
        timeout = arguments.get("timeout", 120)

        if not command:
            return ToolResult(success=False, output="", error="No command provided")

        try:
            if platform.system() == "Windows":
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir,
                    shell=True,
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir,
                    shell=True,
                )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout} seconds",
                )

            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                output += f"\n[STDERR]\n{stderr.decode('utf-8', errors='replace')}"

            success = process.returncode == 0
            output = f"[Exit code: {process.returncode}]\n{output}"

            return ToolResult(success=success, output=output.strip())
        except PermissionError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: {e}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
