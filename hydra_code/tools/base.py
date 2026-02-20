"""
Base tool interface and registry.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from ..clients.base import ToolDefinition


@dataclass
class ToolResult:
    success: bool
    output: str
    error: Optional[str] = None


class Tool(ABC):
    name: str
    description: str

    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        pass

    @abstractmethod
    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        pass


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def get_all_definitions(self) -> list[ToolDefinition]:
        return [tool.get_definition() for tool in self._tools.values()]

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
