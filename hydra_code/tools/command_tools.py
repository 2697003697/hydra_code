"""
Command execution tools.
"""

import asyncio
import re
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

    def _extract_missing_module(self, output: str) -> list[str]:
        """Extract missing module names from error output."""
        modules = set()
        
        patterns = [
            r"ModuleNotFoundError: No module named '([^']+)'",
            r"ImportError: No module named '([^']+)'",
            r"ImportError: cannot import name '([^']+)'",
            r"from '([^']+)'",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, output)
            modules.update(matches)
        
        return list(modules)

    def _extract_package_name(self, module_name: str) -> str:
        """Convert module name to package name."""
        package_map = {
            "pil": "pillow",
            "cv2": "opencv-python",
            "sklearn": "scikit-learn",
            "np": "numpy",
            "pd": "pandas",
            "plt": "matplotlib",
            "sns": "seaborn",
            "yaml": "pyyaml",
            "dotenv": "python-dotenv",
            "websocket": "websocket-client",
            "websockets": "websockets",
            "aiohttp": "aiohttp",
            "httpx": "httpx",
            "bs4": "beautifulsoup4",
            "lxml": "lxml",
            "scipy": "scipy",
            "torch": "torch",
            "tensorflow": "tensorflow",
            "keras": "keras",
            "flask": "flask",
            "django": "django",
            "fastapi": "fastapi",
            "uvicorn": "uvicorn",
            "requests": "requests",
            "urllib3": "urllib3",
            "cryptography": "cryptography",
            "packaging": "packaging",
        }

        return package_map.get(module_name.lower(), module_name.lower())

    async def _run_single_command(self, command: str, working_dir: str, timeout: int) -> tuple[int, str]:
        """Run a single command and return exit code and output."""
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            return -1, f"Command timed out after {timeout} seconds"

        output = ""
        if stdout:
            output += stdout.decode("utf-8", errors="replace")
        if stderr:
            output += f"\n[STDERR]\n{stderr.decode('utf-8', errors='replace')}"

        return process.returncode, output

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        command = arguments.get("command", "")
        timeout = arguments.get("timeout", 120)
        auto_install = arguments.get("auto_install", False)

        if not command:
            return ToolResult(success=False, output="", error="No command provided")

        exit_code, output = await self._run_single_command(command, working_dir, timeout)
        
        if exit_code != 0 and auto_install:
            missing_modules = self._extract_missing_module(output)
            
            if missing_modules:
                output += f"\n\n[自动安装缺失依赖...]"
                
                for module in missing_modules:
                    package_name = self._extract_package_name(module)
                    install_cmd = f"pip install {package_name}"
                    
                    install_output = f"\n尝试安装: {package_name}"
                    output += install_output
                    
                    install_code, install_result = await self._run_single_command(
                        install_cmd, working_dir, 120
                    )
                    
                    if install_code == 0:
                        output += f" ✓ 安装成功\n"
                    else:
                        output += f" ✗ 安装失败: {install_result[:200]}\n"
                
                output += f"\n[重新执行命令...]"
                exit_code, retry_output = await self._run_single_command(command, working_dir, timeout)
                
                output += f"\n{retry_output}"

        output = f"[Exit code: {exit_code}]\n{output}"
        
        if len(output) > 8000:
            output = output[:8000] + f"\n... [输出已截断，原始长度: {len(output)} 字符]"

        success = exit_code == 0
        return ToolResult(success=success, output=output.strip())
