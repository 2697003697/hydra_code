"""
File operation tools.
"""

import os
from pathlib import Path
from typing import Any

from ..clients.base import ToolDefinition
from .base import Tool, ToolResult


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file from the local filesystem. Use this to read file contents."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to read.",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "The line number to start reading from (1-indexed). Default is 1.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read. Default is 2000.",
                    },
                },
                "required": ["file_path"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        file_path = arguments.get("file_path", "")
        if not file_path:
            file_path = arguments.get("path", "")
            
        offset = arguments.get("offset", 1)
        limit = arguments.get("limit", 2000)

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(working_dir) / file_path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")

        if not path.is_file():
            return ToolResult(success=False, output="", error=f"Not a file: {path}")

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            start = max(0, offset - 1)
            end = min(len(lines), start + limit)
            selected_lines = lines[start:end]

            output = ""
            for i, line in enumerate(selected_lines, start=offset):
                output += f"{i:6d}\t{line}"

            return ToolResult(success=True, output=output)
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: Cannot read {path}\nThe file may be locked or you don't have read access.",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file. Creates the file if it doesn't exist, overwrites if it does. ALWAYS provide both file_path (e.g., '/path/to/file.html') and content."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to write. MUST be a file path like '/path/to/file.html', NOT a directory.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file.",
                    },
                },
                "required": ["file_path", "content"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        file_path = arguments.get("file_path", "")
        content = arguments.get("content", "")

        if not file_path:
            # 尝试从 path 参数获取（兼容性处理）
            file_path = arguments.get("path", "")

        if not file_path:
            return ToolResult(
                success=False,
                output="",
                error="No file path provided. Please specify a file path, not a directory.",
            )

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(working_dir) / file_path

        if path.is_dir():
            return ToolResult(
                success=False,
                output="",
                error=f"Path is a directory, not a file: {path}\nPlease specify a file path like: {path}/filename.html",
            )

        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                success=True,
                output=f"Successfully wrote to file: {path}",
            )
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: Cannot write to {path}\nThe file may be locked, read-only, or you don't have write access to this directory.",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class EditFileTool(Tool):
    name = "edit_file"
    description = "Edit a file by replacing a specific section. Use this for making targeted changes to existing files."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to edit.",
                    },
                    "old_content": {
                        "type": "string",
                        "description": "The exact content to find and replace.",
                    },
                    "new_content": {
                        "type": "string",
                        "description": "The new content to replace with.",
                    },
                },
                "required": ["file_path", "old_content", "new_content"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        file_path = arguments.get("file_path", "")
        if not file_path:
            file_path = arguments.get("path", "")
            
        old_content = arguments.get("old_content", "")
        if not old_content:
            old_content = arguments.get("old_str", "")
            
        new_content = arguments.get("new_content", "")
        if not new_content:
            new_content = arguments.get("new_str", "")

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(working_dir) / file_path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            if old_content in content:
                new_file_content = content.replace(old_content, new_content, 1)
            else:
                # Try flexible matching (ignore leading/trailing whitespace per line)
                lines = content.splitlines()
                old_lines = old_content.splitlines()
                
                # Normalize lines for comparison (strip whitespace)
                norm_lines = [l.strip() for l in lines]
                norm_old_lines = [l.strip() for l in old_lines]
                
                # Find the start index
                found_idx = -1
                if not norm_old_lines:
                     return ToolResult(success=False, output="", error="Old content is empty")

                # Simple sliding window search on normalized lines
                # This is O(N*M) but files are usually small enough for this tool
                if norm_old_lines:
                    for i in range(len(norm_lines) - len(norm_old_lines) + 1):
                        match = True
                        for j in range(len(norm_old_lines)):
                            if norm_lines[i+j] != norm_old_lines[j]:
                                match = False
                                break
                        if match:
                            found_idx = i
                            break
                
                if found_idx != -1:
                    # Found a match! Reconstruct the file
                    # We need to replace lines[found_idx : found_idx + len(old_lines)]
                    # with new_content
                    
                    # Check if new_content ends with newline to maintain file structure if needed
                    # But usually new_content is a block. 
                    # We should join the lines before and after.
                    
                    # Be careful: new_content might be a string with newlines, not a list of lines.
                    # We should just insert new_content string.
                    
                    pre_content = "\n".join(lines[:found_idx])
                    if found_idx > 0:
                        pre_content += "\n" # Restore newline after pre-content
                        
                    post_content = "\n".join(lines[found_idx + len(old_lines):])
                    if found_idx + len(old_lines) < len(lines):
                        post_content = "\n" + post_content # Restore newline before post-content
                        
                    new_file_content = pre_content + new_content + post_content
                else:
                    # Final fallback: Try ignoring all whitespace (risky but useful for minified code or messy formats)
                    # For now, let's stick to line-based normalization as it's safer.
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Could not find the content to replace in {path}. Tried exact match and line-based whitespace-insensitive match.",
                    )

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_file_content)

            return ToolResult(
                success=True,
                output=f"Successfully edited file: {path}",
            )
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: Cannot edit {path}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class ListDirectoryTool(Tool):
    name = "list_directory"
    description = "List files and directories in a given path. Use '.' for current directory."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path to the directory to list. Use '.' for current directory.",
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        dir_path = arguments.get("path", ".")

        path = Path(dir_path)
        if not path.is_absolute():
            path = Path(working_dir) / dir_path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"Directory not found: {path}")

        if not path.is_dir():
            return ToolResult(success=False, output="", error=f"Not a directory: {path}")

        try:
            output_lines = []
            for item in sorted(path.iterdir()):
                prefix = "[DIR]  " if item.is_dir() else "       "
                output_lines.append(f"{prefix}{item.name}")

            return ToolResult(success=True, output="\n".join(output_lines))
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: Cannot access {path}\nYou don't have permission to read this directory.",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class SearchFilesTool(Tool):
    name = "search_files"
    description = "Search for files matching a glob pattern in a directory."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match files (e.g., '*.py', '**/*.js').",
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
        pattern = arguments.get("pattern", "*")
        search_path = arguments.get("path", ".")

        path = Path(search_path)
        if not path.is_absolute():
            path = Path(working_dir) / search_path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"Directory not found: {path}")

        try:
            matches = list(path.glob(pattern))
            output_lines = [str(m.relative_to(path)) for m in sorted(matches)]
            return ToolResult(success=True, output="\n".join(output_lines))
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: Cannot search in {path}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class DeleteFileTool(Tool):
    name = "delete_file"
    description = "Delete a file or directory. Use with caution."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file or directory to delete.",
                    },
                },
                "required": ["file_path"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        file_path = arguments.get("file_path", "")

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(working_dir) / file_path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {path}")

        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                import shutil
                shutil.rmtree(path)
            
            return ToolResult(success=True, output=f"Successfully deleted: {path}")
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: Cannot delete {path}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class CreateDirectoryTool(Tool):
    name = "create_directory"
    description = "Create a new directory. Creates parent directories if needed."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "directory_path": {
                        "type": "string",
                        "description": "The absolute path of the directory to create.",
                    },
                },
                "required": ["directory_path"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        dir_path = arguments.get("directory_path", "")

        path = Path(dir_path)
        if not path.is_absolute():
            path = Path(working_dir) / dir_path

        try:
            path.mkdir(parents=True, exist_ok=True)
            return ToolResult(success=True, output=f"Successfully created directory: {path}")
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: Cannot create directory {path}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class MoveFileTool(Tool):
    name = "move_file"
    description = "Move or rename a file or directory."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "The source file or directory path.",
                    },
                    "destination": {
                        "type": "string",
                        "description": "The destination file or directory path.",
                    },
                },
                "required": ["source", "destination"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        source = arguments.get("source", "")
        destination = arguments.get("destination", "")

        src_path = Path(source)
        if not src_path.is_absolute():
            src_path = Path(working_dir) / source

        dst_path = Path(destination)
        if not dst_path.is_absolute():
            dst_path = Path(working_dir) / destination

        if not src_path.exists():
            return ToolResult(success=False, output="", error=f"Source not found: {src_path}")

        try:
            import shutil
            shutil.move(str(src_path), str(dst_path))
            return ToolResult(
                success=True,
                output=f"Successfully moved {src_path} to {dst_path}",
            )
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: Cannot move {src_path}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class CopyFileTool(Tool):
    name = "copy_file"
    description = "Copy a file or directory."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "The source file or directory path.",
                    },
                    "destination": {
                        "type": "string",
                        "description": "The destination file or directory path.",
                    },
                },
                "required": ["source", "destination"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        source = arguments.get("source", "")
        destination = arguments.get("destination", "")

        src_path = Path(source)
        if not src_path.is_absolute():
            src_path = Path(working_dir) / source

        dst_path = Path(destination)
        if not dst_path.is_absolute():
            dst_path = Path(working_dir) / destination

        if not src_path.exists():
            return ToolResult(success=False, output="", error=f"Source not found: {src_path}")

        try:
            import shutil
            if src_path.is_file():
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src_path), str(dst_path))
            else:
                shutil.copytree(str(src_path), str(dst_path))
            
            return ToolResult(
                success=True,
                output=f"Successfully copied {src_path} to {dst_path}",
            )
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: Cannot copy {src_path}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class GetFileInfoTool(Tool):
    name = "get_file_info"
    description = "Get detailed information about a file or directory (size, modification time, etc.)."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file or directory.",
                    },
                },
                "required": ["file_path"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        import datetime
        
        file_path = arguments.get("file_path", "")

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(working_dir) / file_path

        if not path.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {path}")

        try:
            stat = path.stat()
            
            info = [
                f"Path: {path}",
                f"Type: {'Directory' if path.is_dir() else 'File'}",
                f"Size: {stat.st_size:,} bytes",
                f"Created: {datetime.datetime.fromtimestamp(stat.st_ctime).isoformat()}",
                f"Modified: {datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()}",
                f"Accessed: {datetime.datetime.fromtimestamp(stat.st_atime).isoformat()}",
            ]
            
            if path.is_file():
                info.append(f"Extension: {path.suffix}")
                info.append(f"Permissions: {oct(stat.st_mode)[-3:]}")
            
            return ToolResult(success=True, output="\n".join(info))
        except PermissionError:
            return ToolResult(
                success=False,
                output="",
                error=f"Permission denied: Cannot access {path}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
