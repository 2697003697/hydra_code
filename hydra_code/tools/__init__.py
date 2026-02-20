"""
Tool system for Hydra Code.
Provides file operations, command execution, and codebase understanding.
"""

from .base import Tool, ToolRegistry, ToolResult
from .file_tools import (
    ReadFileTool, WriteFileTool, EditFileTool, ListDirectoryTool, SearchFilesTool,
    DeleteFileTool, CreateDirectoryTool, MoveFileTool, CopyFileTool, GetFileInfoTool,
)
from .command_tools import RunCommandTool
from .codebase_tools import SearchCodebaseTool
from .network_tools import FetchUrlTool

__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ListDirectoryTool",
    "SearchFilesTool",
    "DeleteFileTool",
    "CreateDirectoryTool",
    "MoveFileTool",
    "CopyFileTool",
    "GetFileInfoTool",
    "RunCommandTool",
    "SearchCodebaseTool",
    "FetchUrlTool",
    "get_default_tools",
]


def get_default_tools() -> list[Tool]:
    return [
        ReadFileTool(),
        WriteFileTool(),
        EditFileTool(),
        ListDirectoryTool(),
        SearchFilesTool(),
        DeleteFileTool(),
        CreateDirectoryTool(),
        MoveFileTool(),
        CopyFileTool(),
        GetFileInfoTool(),
        RunCommandTool(),
        SearchCodebaseTool(),
        FetchUrlTool(),
    ]
