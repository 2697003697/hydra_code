"""
Network tools.
"""

import asyncio
from typing import Any

import httpx

from ..clients.base import ToolDefinition
from .base import Tool, ToolResult


class FetchUrlTool(Tool):
    name = "fetch_url"
    description = "Fetch content from a URL. Returns the content as text."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds. Default is 30.",
                    },
                },
                "required": ["url"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        url = arguments.get("url", "")
        timeout = arguments.get("timeout", 30)

        if not url:
            return ToolResult(success=False, output="", error="No URL provided")

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                
                content_type = response.headers.get("content-type", "")
                
                if "text" in content_type or "application/json" in content_type or "application/xml" in content_type:
                    text = response.text
                    if len(text) > 50000:
                        text = text[:50000] + "\n... [truncated]"
                    return ToolResult(success=True, output=text)
                else:
                    return ToolResult(
                        success=True,
                        output=f"Binary content: {content_type}\nSize: {len(response.content):,} bytes",
                    )
        except httpx.TimeoutException:
            return ToolResult(
                success=False,
                output="",
                error=f"Request timed out after {timeout} seconds",
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"HTTP error {e.response.status_code}: {e.response.reason_phrase}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
