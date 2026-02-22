"""
Network tools.
"""

import asyncio
import re
import json
from typing import Any
from xml.etree import ElementTree

import httpx

from ..clients.base import ToolDefinition
from .base import Tool, ToolResult


def extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML, removing scripts, styles, and tags."""
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<aside[^>]*>.*?</aside>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = re.sub(r'\s+', ' ', html)
    html = re.sub(r'\n\s*\n', '\n\n', html)
    return html.strip()


def parse_rss_feed(xml_content: str) -> str:
    """Parse RSS/Atom feed and extract articles."""
    try:
        root = ElementTree.fromstring(xml_content)
    except ElementTree.ParseError:
        return None
    
    results = []
    
    atom_ns = '{http://www.w3.org/2005/Atom}'
    
    if root.tag == f'{atom_ns}feed':
        entries = root.findall(f'{atom_ns}entry')
        for entry in entries[:10]:
            title_elem = entry.find(f'{atom_ns}title')
            link_elem = entry.find(f'{atom_ns}link')
            summary_elem = entry.find(f'{atom_ns}summary') or entry.find(f'{atom_ns}content')
            
            title = title_elem.text if title_elem is not None else "无标题"
            link = link_elem.get('href') if link_elem is not None else ""
            summary = ""
            if summary_elem is not None and summary_elem.text:
                summary = summary_elem.text[:300]
                if len(summary_elem.text) > 300:
                    summary += "..."
            
            results.append(f"### {title}\n{summary}\n链接: {link}\n")
    
    elif root.tag == 'rss' or root.tag.endswith('rss'):
        channel = root.find('channel')
        if channel is not None:
            items = channel.findall('item')
            for item in items[:10]:
                title_elem = item.find('title')
                link_elem = item.find('link')
                desc_elem = item.find('description')
                
                title = title_elem.text if title_elem is not None else "无标题"
                link = link_elem.text if link_elem is not None else ""
                desc = ""
                if desc_elem is not None and desc_elem.text:
                    desc = re.sub(r'<[^>]+>', '', desc_elem.text)[:300]
                    if len(desc_elem.text) > 300:
                        desc += "..."
                
                results.append(f"### {title}\n{desc}\n链接: {link}\n")
    
    if results:
        return "# RSS/Atom Feed 内容\n\n" + "\n---\n".join(results)
    return None


def smart_truncate(text: str, max_length: int = 4000) -> str:
    """Intelligently truncate text, trying to keep complete paragraphs."""
    if len(text) <= max_length:
        return text
    
    truncated = text[:max_length]
    
    last_para = truncated.rfind('\n\n')
    last_sentence = truncated.rfind('。')
    last_period = truncated.rfind('.')
    
    cut_point = max(last_para, last_sentence, last_period)
    if cut_point > max_length * 0.7:
        truncated = truncated[:cut_point + 1]
    
    return truncated + f"\n\n... [内容已截断，原始长度: {len(text)} 字符]"


class FetchUrlTool(Tool):
    name = "fetch_url"
    description = "Fetch content from a URL. Automatically extracts readable text from HTML or parses RSS feeds. Use max_length to control output size."

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
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum length of returned content in characters. Default is 4000. Set higher for detailed content.",
                    },
                    "raw": {
                        "type": "boolean",
                        "description": "If true, return raw content without processing. Default is false.",
                    },
                },
                "required": ["url"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        url = arguments.get("url", "")
        timeout = arguments.get("timeout", 30)
        max_length = arguments.get("max_length", 4000)
        raw_mode = arguments.get("raw", False)

        if not url:
            return ToolResult(success=False, output="", error="No URL provided")

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                
                content_type = response.headers.get("content-type", "")
                
                if raw_mode:
                    text = response.text
                    return ToolResult(success=True, output=smart_truncate(text, max_length))
                
                if "xml" in content_type or url.endswith((".xml", ".rss", ".atom")):
                    rss_result = parse_rss_feed(response.text)
                    if rss_result:
                        return ToolResult(success=True, output=smart_truncate(rss_result, max_length))
                
                if "text/html" in content_type or "html" in content_type:
                    text = extract_text_from_html(response.text)
                    return ToolResult(success=True, output=smart_truncate(text, max_length))
                
                if "application/json" in content_type:
                    try:
                        data = json.loads(response.text)
                        formatted = json.dumps(data, ensure_ascii=False, indent=2)
                        return ToolResult(success=True, output=smart_truncate(formatted, max_length))
                    except json.JSONDecodeError:
                        return ToolResult(success=True, output=smart_truncate(response.text, max_length))
                
                if "text" in content_type:
                    return ToolResult(success=True, output=smart_truncate(response.text, max_length))
                
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


class SearchWebTool(Tool):
    """Search the web using a search API (requires configuration)."""
    name = "search_web"
    description = "Search the web for information. Returns top results with titles and snippets."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return. Default is 5.",
                    },
                },
                "required": ["query"],
            },
        )

    async def execute(self, arguments: dict[str, Any], working_dir: str) -> ToolResult:
        query = arguments.get("query", "")
        num_results = arguments.get("num_results", 5)

        if not query:
            return ToolResult(success=False, output="", error="No search query provided")

        return ToolResult(
            success=False,
            output="",
            error="Web search is not configured. Please set up a search API key in config.",
        )
