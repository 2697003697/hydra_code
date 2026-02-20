"""
Codebase understanding tools.
"""

import os
import re
from pathlib import Path
from typing import Any

from ..clients.base import ToolDefinition
from .base import Tool, ToolResult


class SearchCodebaseTool(Tool):
    name = "search_code"
    description = "Search for text patterns in code files using regex. Use this to find code across the project."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The regex pattern or text to search for.",
                    },
                    "path": {
                        "type": "string",
                        "description": "The directory to search in. Use '.' for current directory.",
                    },
                },
                "required": ["pattern"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        pattern = arguments.get("pattern", "")
        search_path = arguments.get("path", ".")

        if not pattern:
            return ToolResult(success=False, output="", error="No pattern provided")

        path = Path(search_path)
        if not path.is_absolute():
            path = Path(working_dir) / search_path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"Directory not found: {path}")

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            try:
                regex = re.compile(re.escape(pattern), re.IGNORECASE)
            except re.error:
                return ToolResult(success=False, output="", error=f"Invalid regex: {e}")

        ignore_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist", ".idea", ".vscode"}
        results = []

        try:
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in ignore_dirs]

                for file in files:
                    if not file.endswith((".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".h", ".html", ".css", ".json", ".yaml", ".yml", ".md", ".txt")):
                        continue

                    file_path = Path(root) / file

                    try:
                        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                            lines = f.readlines()

                        for i, line in enumerate(lines):
                            if regex.search(line):
                                start = max(0, i - 2)
                                end = min(len(lines), i + 3)

                                context = []
                                for j in range(start, end):
                                    prefix = ">>> " if j == i else "    "
                                    context.append(f"{prefix}{j + 1:5d}: {lines[j].rstrip()}")

                                rel_path = file_path.relative_to(path)
                                results.append(f"\n{rel_path}:\n" + "\n".join(context))
                    except Exception:
                        continue

            if not results:
                return ToolResult(success=True, output="No matches found.")

            return ToolResult(success=True, output="\n".join(results[:50]))
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: Cannot search in {path}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
