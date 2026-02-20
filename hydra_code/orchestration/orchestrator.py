"""
Multi-model orchestrator for parallel execution and coordination.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from rich.console import Console
from rich.live import Live
from rich.text import Text

from ..clients import Message, Role, create_client
from ..config import Config
from ..tools import ToolRegistry, get_default_tools
from .roles import ModelRole, get_role_definition
from .dispatcher import TaskAnalysis, TaskDispatcher, TaskType, SubTask
from .aggregator import AggregatedResult, ModelResult, ResultAggregator

console = Console()


@dataclass
class ModelClient:
    role: ModelRole
    model_name: str
    client: Any
    max_tokens: Optional[int] = None


@dataclass
class ExecutionContext:
    working_dir: str
    messages: list[Message] = field(default_factory=list)
    tool_registry: ToolRegistry = field(default_factory=ToolRegistry)


class MultiModelOrchestrator:
    def __init__(self, config: Config, working_dir: str):
        self.config = config
        self.working_dir = working_dir
        self.dispatcher = TaskDispatcher()
        self.aggregator = ResultAggregator()
        self.clients: dict[ModelRole, ModelClient] = {}
        self.tool_registry = ToolRegistry()
        self.messages: list[Message] = []
        
        self._setup_tools()
        self._setup_clients()

    def _setup_tools(self):
        for tool in get_default_tools():
            self.tool_registry.register(tool)

    def _setup_clients(self):
        for role in ModelRole:
            api_key, base_url, model_name, provider, max_tokens = self.config.get_role_config(role.value)
            
            if api_key and base_url and model_name:
                client = create_client(
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name,
                    provider=provider,
                )
                self.clients[role] = ModelClient(
                    role=role,
                    model_name=model_name,
                    client=client,
                    max_tokens=max_tokens,
                )

    def _get_system_prompt(self, role: ModelRole) -> str:
        role_def = get_role_definition(role)
        base_prompt = f"""你是一个AI代码助手。

当前工作目录: {self.working_dir}

你有以下工具可用:
- read_file: 读取文件
- write_file: 写入文件
- edit_file: 编辑文件
- list_directory: 列出目录
- search_files: 搜索文件
- run_command: 执行命令
- search_code: 搜索代码

{role_def.system_prompt_suffix}
"""
        return base_prompt

    async def process_message(
        self,
        user_input: str,
        on_content: Optional[Callable[[str], None]] = None,
    ) -> AggregatedResult:
        self.messages.append(Message(role=Role.USER, content=user_input))
        
        analysis = self.dispatcher.analyze(user_input)
        
        if analysis.task_type == TaskType.SIMPLE:
            return await self._handle_simple_task(user_input, on_content)
        
        return await self._handle_complex_task(analysis, user_input, on_content)

    async def _handle_simple_task(
        self,
        user_input: str,
        on_content: Optional[Callable[[str], None]] = None,
    ) -> AggregatedResult:
        if ModelRole.FAST not in self.clients:
            available_role = next(iter(self.clients.keys()))
            return await self._execute_single_role(
                available_role, user_input, on_content
            )
        
        result = await self._execute_single_role(
            ModelRole.FAST, user_input, on_content
        )
        
        parsed = self.dispatcher.parse_dispatcher_response(result.content)
        if parsed and parsed.subtasks:
            return await self._handle_complex_task(parsed, user_input, on_content)
        
        return AggregatedResult(
            success=result.success,
            content=result.content,
            role_results={result.role: result},
            summary="简单任务由 Fast 直接处理",
        )

    async def _handle_complex_task(
        self,
        analysis: TaskAnalysis,
        user_input: str,
        on_content: Optional[Callable[[str], None]] = None,
    ) -> AggregatedResult:
        console.print(f"\n[dim]任务分析: {analysis.analysis}[/dim]")
        
        independent_tasks = []
        dependent_tasks = []
        
        for subtask in analysis.subtasks:
            if subtask.dependencies:
                dependent_tasks.append(subtask)
            else:
                independent_tasks.append(subtask)
        
        results: list[ModelResult] = []
        
        if independent_tasks:
            console.print(f"[dim]并发执行 {len(independent_tasks)} 个独立子任务...[/dim]")
            parallel_results = await self._execute_parallel(independent_tasks, on_content)
            results.extend(parallel_results)
        
        if dependent_tasks:
            for subtask in dependent_tasks:
                context = self._build_context(results, subtask.dependencies)
                result = await self._execute_subtask(subtask, context, on_content)
                results.append(result)
        
        return self.aggregator.aggregate(results)

    async def _execute_parallel(
        self,
        subtasks: list[SubTask],
        on_content: Optional[Callable[[str], None]] = None,
    ) -> list[ModelResult]:
        tasks = [
            self._execute_subtask(st, {}, on_content)
            for st in subtasks
            if st.role in self.clients
        ]
        
        if not tasks:
            return []
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        model_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                model_results.append(ModelResult(
                    role=subtasks[i].role,
                    success=False,
                    content="",
                    error=str(result),
                ))
            else:
                model_results.append(result)
        
        return model_results

    async def _execute_subtask(
        self,
        subtask: SubTask,
        context: dict[str, Any],
        on_content: Optional[Callable[[str], None]] = None,
    ) -> ModelResult:
        return await self._execute_single_role(
            subtask.role, subtask.task, on_content, context
        )

    async def _execute_single_role(
        self,
        role: ModelRole,
        task: str,
        on_content: Optional[Callable[[str], None]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> ModelResult:
        if role not in self.clients:
            return ModelResult(
                role=role,
                success=False,
                content="",
                error=f"模型 {role.value} 不可用",
            )
        
        model_client = self.clients[role]
        role_def = get_role_definition(role)
        
        console.print(f"[dim]→ {role_def.name} 处理中...[/dim]")
        
        messages = [
            Message(role=Role.SYSTEM, content=self._get_system_prompt(role)),
            Message(role=Role.USER, content=task),
        ]
        
        if context and context.get("previous_results"):
            context_msg = "之前的执行结果:\n" + "\n".join(context["previous_results"])
            messages.append(Message(role=Role.USER, content=context_msg))
        
        tools = self.tool_registry.get_all_definitions()
        
        start_time = time.time()
        stream_buffer: list[str] = []
        
        try:
            text_widget = Text("")
            
            with Live(text_widget, console=console, refresh_per_second=30, transient=True):
                response = await model_client.client.chat_stream(
                    messages=messages,
                    tools=tools,
                    max_tokens=model_client.max_tokens or self.config.max_tokens,
                    temperature=self.config.temperature,
                    on_content=on_content,
                )
            
            execution_time = time.time() - start_time
            
            tool_calls_data = []
            if response.tool_calls:
                tool_calls_data = [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in response.tool_calls
                ]
                
                await self._process_tool_calls(response.tool_calls)
            
            return ModelResult(
                role=role,
                success=True,
                content=response.content or "",
                tool_calls=tool_calls_data,
                execution_time=execution_time,
            )
            
        except Exception as e:
            return ModelResult(
                role=role,
                success=False,
                content="",
                error=str(e),
                execution_time=time.time() - start_time,
            )

    async def _process_tool_calls(self, tool_calls: list[Any]) -> list[dict]:
        results = []
        for tc in tool_calls:
            tool = self.tool_registry.get(tc.name)
            if tool:
                result = await tool.execute(tc.arguments, self.working_dir)
                results.append({
                    "tool": tc.name,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                })
        return results

    def _build_context(
        self,
        results: list[ModelResult],
        dependencies: list[str],
    ) -> dict[str, Any]:
        context: dict[str, Any] = {"previous_results": []}
        
        for result in results:
            if result.success and result.content:
                role_def = get_role_definition(result.role)
                context["previous_results"].append(
                    f"[{role_def.name}]: {result.content[:500]}"
                )
        
        return context

    def get_available_roles(self) -> list[ModelRole]:
        return list(self.clients.keys())

    def get_status(self) -> dict[str, Any]:
        return {
            "available_models": [
                {
                    "role": role.value,
                    "model": self.clients[role].model_name,
                }
                for role in self.clients
            ],
            "working_directory": self.working_dir,
        }
