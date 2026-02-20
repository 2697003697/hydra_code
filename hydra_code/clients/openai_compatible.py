"""
OpenAI-compatible API client.
Works with StepFun, Qwen, DeepSeek, GLM and other OpenAI-compatible APIs.
"""

import json
from typing import Any, AsyncIterator, Callable, Optional

import httpx
from openai import AsyncOpenAI, AsyncAzureOpenAI
from rich.console import Console

from .base import BaseClient, Message, Role, ToolCall, ToolDefinition

console = Console()


class OpenAICompatibleClient(BaseClient):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        enable_reasoning: bool = True,
        provider: str = "openai",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.enable_reasoning = enable_reasoning
        self.provider = provider.lower()
        
        if self.provider == "azure":
             self._client = AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=base_url,
                api_version="2024-05-01-preview", # Default version, maybe should be configurable
                http_client=httpx.AsyncClient(timeout=120.0),
            )
        else:
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                http_client=httpx.AsyncClient(timeout=120.0),
            )

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        result = []
        for msg in messages:
            if msg.role == Role.TOOL:
                result.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id or "",
                    "content": msg.content or "",
                })
            else:
                result.append(msg.to_dict())
        return result

    def _convert_tools(self, tools: Optional[list[ToolDefinition]]) -> Optional[list[dict[str, Any]]]:
        if not tools:
            return None
        return [tool.to_dict() for tool in tools]

    def _parse_tool_calls(self, tool_calls_data: list[Any]) -> list[ToolCall]:
        result = []
        for tc in tool_calls_data:
            args = tc.function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            result.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=args,
            ))
        return result

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> Message:
        converted_messages = self._convert_messages(messages)
        converted_tools = self._convert_tools(tools)

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": converted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if converted_tools:
            kwargs["tools"] = converted_tools
        
        if self.enable_reasoning:
            # DeepSeek specific handling
            if self.provider == "deepseek" or "deepseek" in self.base_url.lower():
                 kwargs["reasoning_effort"] = "high"
            # Generic thinking enabling (if supported by provider via extra_body)
            else:
                kwargs["extra_body"] = {
                    "enable_thinking": True,
                }

        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        content = choice.message.content
        tool_calls = None

        if choice.message.tool_calls:
            tool_calls = self._parse_tool_calls(choice.message.tool_calls)
        
        reasoning_content = None
        if hasattr(choice.message, "reasoning_content"):
            reasoning_content = choice.message.reasoning_content

        return Message(
            role=Role.ASSISTANT,
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls or [],
        )

    async def chat_stream(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        on_content: Optional[Callable[[str], None]] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
        on_tool_update: Optional[Callable[[str, str], None]] = None,
    ) -> Message:
        converted_messages = self._convert_messages(messages)
        converted_tools = self._convert_tools(tools)

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": converted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        if converted_tools:
            kwargs["tools"] = converted_tools
        
        # DeepSeek reasoning effort handling
        if self.enable_reasoning and (self.provider == "deepseek" or "deepseek" in self.base_url.lower()):
             kwargs["reasoning_effort"] = "high"

        stream = await self._client.chat.completions.create(**kwargs)

        content_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls_map: dict[int, dict[str, Any]] = {}
        finish_reason = None
        has_tool_calls = False

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta
            
            if hasattr(chunk.choices[0], 'finish_reason') and chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
            
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                if on_thinking:
                    on_thinking(delta.reasoning_content)
                thinking_parts.append(delta.reasoning_content)

            if delta.content:
                if on_content:
                    on_content(delta.content)
                content_parts.append(delta.content)

            if delta.tool_calls:
                has_tool_calls = True
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }
                    
                    current_tool = tool_calls_map[idx]
                    
                    if tc.id:
                        current_tool["id"] = tc.id
                    
                    if tc.function:
                        if tc.function.name:
                            current_tool["name"] = tc.function.name
                        
                        if tc.function.arguments:
                            current_tool["arguments"] += tc.function.arguments
                            if on_tool_update:
                                # 传递当前工具名称和参数片段
                                on_tool_update(current_tool["name"], tc.function.arguments)

        content = "".join(content_parts) or None
        reasoning_content = "".join(thinking_parts) or None
        tool_calls = []
        
        # 从 map 中构建最终的 tool_calls 列表
        if tool_calls_map:
            for idx in sorted(tool_calls_map.keys()):
                tc_data = tool_calls_map[idx]
                try:
                    args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json.JSONDecodeError:
                    args = {} # 或者保留原始字符串？这里为了兼容性还是转为空字典比较安全
                
                tool_calls.append(ToolCall(
                    id=tc_data["id"] or f"call_{idx}",
                    name=tc_data["name"],
                    arguments=args
                ))

        # 之前的非流式回退逻辑在这里可能不再需要，或者需要保留作为双重保险？
        # 如果流式解析成功，就不需要回退了。
        # 但之前的逻辑是只要有 tool_calls 就回退，可能是为了确保 JSON 完整性。
        # 既然我们现在要流式显示工具参数，那么我们必须依赖流式输出。
        # 如果流式输出 JSON 不完整，那是模型问题。
        # 我们暂时注释掉回退逻辑，完全依赖流式解析。
        
        return Message(
            role=Role.ASSISTANT,
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
        )

    def supports_tools(self) -> bool:
        return True


def create_client(
    api_key: str,
    base_url: str,
    model_name: str,
    enable_reasoning: bool = True,
    provider: str = "openai",
) -> BaseClient:
    return OpenAICompatibleClient(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        enable_reasoning=enable_reasoning,
        provider=provider,
    )
