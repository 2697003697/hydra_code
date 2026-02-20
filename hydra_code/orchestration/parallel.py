"""
Parallel collaboration system with multi-instance support.
Implements: Architecture → Parallel Execution → Dynamic Collaboration → Integration
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Callable
from enum import Enum

from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from .roles import ModelRole
from ..clients import Message, Role
from ..tools import ToolRegistry
from .. import stats
from ..todo import TodoList, TaskStatus as TodoStatus
from ..ui import ui, TodoListRenderer

console = Console()


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_HELP = "needs_help"


@dataclass
class ParallelTask:
    id: str
    description: str
    role: ModelRole
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: str = ""
    code_output: str = ""
    issues: list[str] = field(default_factory=list)
    assigned_instance: int = 0


@dataclass
class ModuleSpec:
    name: str
    description: str
    interface: str
    role: ModelRole


@dataclass
class ArchitecturePlan:
    modules: list[ModuleSpec]
    interfaces: dict[str, str]
    execution_order: list[list[str]]
    tech_stack: str = ""
    domain: str = "coding"


from rich.live import Live

class ParallelCollaborator:
    """Manages parallel execution with multiple model instances."""
    
    def __init__(
        self,
        agents: dict[ModelRole, Any],
        tool_registry: ToolRegistry,
        working_dir: str,
        max_instances_per_role: int = 2,
        on_progress: Optional[Callable[[str, str, int, int], None]] = None,
        domain: str = "coding",
    ):
        self.agents = agents
        self.tool_registry = tool_registry
        self.working_dir = working_dir
        self.max_instances = max_instances_per_role
        self.tasks: dict[str, ParallelTask] = {}
        self.architecture: Optional[ArchitecturePlan] = None
        self.on_progress = on_progress
        self.domain = domain
        self._current_phase = ""
        self._current_task = ""
        self._progress_current = 0
        self._progress_total = 0
        self.todo_list = TodoList(title="Architecture Plan")
    
    def _update_progress(self, phase: str, task: str, current: int = 0, total: int = 0):
        self._current_phase = phase
        self._current_task = task
        self._progress_current = current
        self._progress_total = total
        
        if self.on_progress:
            self.on_progress(phase, task, current, total)

    def _update_todo_item(self, module_name: str, status: TaskStatus):
        """Update todo item status."""
        todo_status = TodoStatus.PENDING
        if status == TaskStatus.IN_PROGRESS:
            todo_status = TodoStatus.IN_PROGRESS
        elif status == TaskStatus.COMPLETED:
            todo_status = TodoStatus.COMPLETED
        elif status == TaskStatus.FAILED:
            todo_status = TodoStatus.FAILED
        elif status == TaskStatus.NEEDS_HELP:
            todo_status = TodoStatus.IN_PROGRESS
            
        for item in self.todo_list.items:
            if item.id == module_name:
                item.status = todo_status
                break

        
    async def execute(
        self,
        user_request: str,
        context: str = "",
    ) -> str:
        """Execute parallel collaboration workflow."""
        
        self._update_progress("架构设计", "正在分析需求...", 0, 3)
        
        ui.print_phase("架构设计", "Pro 分析需求并设计模块结构")
        self.architecture = await self._design_architecture(user_request, context)
        
        if not self.architecture or not self.architecture.modules:
            ui.print_error("架构设计失败")
            return "架构设计失败"
        
        modules_info = [
            {"name": m.name, "role": m.role.value, "completed": False, "in_progress": False}
            for m in self.architecture.modules
        ]
        ui.print_module_status(modules_info)
        
        self._update_progress("并行实现", "准备并行执行...", 1, 3)
        
        ui.print_phase("并行实现", "各模型并行实现模块")
        await self._parallel_execution(user_request, context)
        
        self._update_progress("整合验证", "正在整合模块...", 2, 3)
        
        ui.print_phase("整合验证", "Opus 整合所有模块")
        result = await self._integrate_modules(user_request, context)
        
        self._update_progress("完成", "任务完成", 3, 3)
        console.print(TodoListRenderer(self.todo_list))
        
        return result
    
    async def _design_architecture(
        self,
        user_request: str,
        context: str,
    ) -> ArchitecturePlan:
        """Pro designs the overall architecture."""
        pro_agent = self.agents.get(ModelRole.PRO)
        if not pro_agent:
             pro_agent = next(iter(self.agents.values())) if self.agents else None
        
        if not pro_agent:
             return self._create_default_architecture(user_request)
        
        # Select prompt based on domain
        if self.domain == "content":
            prompt = f"""分析以下创作需求，设计内容大纲。

用户需求: {user_request}

上下文:
{context}

请输出JSON格式:
{{
  "tech_stack": "内容格式与风格（如 Markdown, 学术论文, 轻松博客等）",
  "modules": [
    {{
      "name": "章节名称",
      "description": "本章核心内容与目标",
      "interface": "关键要点（Key Points）与字数预估",
      "role": "fast/pro/sonnet/opus"
    }}
  ],
  "interfaces": {{
    "章节名称": "详细的大纲或写作指导"
  }},
  "execution_order": [
    ["可以并行创作的章节列表"],
    ["下一批章节"]
  ]
}}

要求:
1. 确定统一的文风和格式。
2. 将内容拆解为独立的章节或部分。
3. 确保各部分逻辑连贯。
4. 为每个部分分配适合的角色。
"""
        else:
            # Default Coding Prompt
            prompt = f"""分析以下需求，设计软件架构。

用户需求: {user_request}

上下文:
{context}

请输出JSON格式:
{{
  "tech_stack": "统一的技术栈（如 Python CLI, HTML5/JS, React+Node 等）",
  "modules": [
    {{
      "name": "模块名",
      "description": "模块职责（必须符合统一技术栈）",
      "interface": "接口定义（函数签名、数据结构）",
      "role": "fast/pro/sonnet/opus"
    }}
  ],
  "interfaces": {{
    "模块名": "该模块对外暴露的接口详情"
  }},
  "execution_order": [
    ["可以并行执行的模块名列表"],
    ["下一批并行模块"]
  ]
}}

要求:
1. 必须首先确定一个【统一的技术栈】。例如：如果是游戏，决定是纯Python控制台版，还是HTML5网页版，不要混合！
2. 将任务分解为3-6个模块，所有模块必须属于同一个应用，协同工作。
3. 严禁创建两个独立的应用版本（例如：不要同时做一个Python版和一个Web版）。
4. 每个模块分配最适合的角色。
5. 明确模块间的接口依赖。
6. 可以并行的模块放在同一批次。"""

        messages = [
            Message(role=Role.SYSTEM, content=f"你是 Pro 模型，负责将复杂任务分解为可并行的子任务。当前任务领域: {self.domain}"),
            Message(role=Role.USER, content=prompt)
        ]
        
        response = await self._call_agent(pro_agent, messages)
        
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]+\}', response)
            if not json_match:
                raise ValueError("No JSON found in response")
                
            plan_dict = json.loads(json_match.group())
            
            modules = []
            for m in plan_dict["modules"]:
                # Convert role string to Enum
                role_str = m.get("role", "pro")
                try:
                    role = ModelRole(role_str.lower())
                except ValueError:
                    role = ModelRole.PRO
                
                modules.append(ModuleSpec(
                    name=m.get("name", "unknown"),
                    description=m.get("description", ""),
                    interface=m.get("interface", ""),
                    role=role
                ))
            
            self.architecture = ArchitecturePlan(
                modules=modules,
                interfaces=plan_dict.get("interfaces", {}),
                execution_order=plan_dict.get("execution_order", []),
                tech_stack=plan_dict.get("tech_stack", ""),
                domain=self.domain
            )
            
            # Populate TodoList
            self.todo_list.clear()
            for module in modules:
                self.todo_list.add_task(
                    content=f"{module.name}: {module.description}", 
                    id=module.name
                )
            console.print(TodoListRenderer(self.todo_list))
            
            return self.architecture
            
        except Exception as e:
            console.print(f"[red]架构设计失败: {e}[/red]")
            # Fallback simple plan
            return ArchitecturePlan(
                modules=[ModuleSpec(
                    name="core",
                    description="Core implementation",
                    interface="main",
                    role=ModelRole.SONNET
                )],
                interfaces={},
                execution_order=[["core"]],
                tech_stack="Default",
                domain=self.domain
            )
    
    def _create_default_architecture(self, user_request: str) -> ArchitecturePlan:
        """Create a default architecture when parsing fails."""
        console.print(f"[cyan]使用默认架构方案[/cyan]")
        
        modules = [
            ModuleSpec(
                name="core",
                description="核心功能实现",
                interface="主要业务逻辑和数据结构",
                role=ModelRole.PRO,
            ),
            ModuleSpec(
                name="ui",
                description="用户界面实现",
                interface="HTML/CSS/JS界面组件",
                role=ModelRole.SONNET,
            ),
            ModuleSpec(
                name="integration",
                description="整合与测试",
                interface="模块集成和最终验证",
                role=ModelRole.OPUS,
            ),
        ]
        
        return ArchitecturePlan(
            modules=modules,
            interfaces={m.name: m.interface for m in modules},
            execution_order=[["core", "ui"], ["integration"]],
            tech_stack="Python/HTML5混合"
        )
    
    async def _parallel_execution(
        self,
        user_request: str,
        context: str,
    ):
        """Execute modules in parallel batches."""
        if not self.architecture:
            return
        
        total_modules = len(self.architecture.modules)
        completed_modules = 0
        
        for i, module in enumerate(self.architecture.modules):
            task_id = f"module_{i}"
            self.tasks[task_id] = ParallelTask(
                id=task_id,
                description=f"实现 {module.name}: {module.description}",
                role=module.role,
            )
        
        # Setup Monitor
        monitor = ui.create_parallel_monitor("并行执行")
        
        with Live(monitor, refresh_per_second=10) as live:
            for batch_idx, batch in enumerate(self.architecture.execution_order):
                monitor.add_log(f"批次 {batch_idx + 1}: 并行执行 {len(batch)} 个模块")
                
                self._update_progress(
                    "并行实现", 
                    f"批次 {batch_idx + 1}: {', '.join(batch)}", 
                    completed_modules, 
                    total_modules
                )
                
                coroutines = []
                for module_name in batch:
                    task = self._find_task_by_module_name(module_name)
                    if task:
                        module = self._find_module_by_name(module_name)
                        if module:
                            monitor.update_task(module.name, "Pending")
                            coroutines.append(
                                self._execute_module(task, module, user_request, context, monitor)
                            )
                
                if coroutines:
                    await asyncio.gather(*coroutines, return_exceptions=True)
                
                completed_modules += len(batch)
                self._update_progress("并行实现", f"已完成 {completed_modules}/{total_modules} 模块", completed_modules, total_modules)
    
    async def _execute_module(
        self,
        task: ParallelTask,
        module: ModuleSpec,
        user_request: str,
        context: str,
        monitor: Any = None,
    ):
        """Execute a single module with tool support."""
        agent = self.agents.get(task.role)
        if not agent:
            task.status = TaskStatus.FAILED
            self._update_todo_item(module.name, task.status)
            task.issues.append(f"找不到 {task.role.value} 模型")
            if monitor:
                monitor.update_task(module.name, "Failed: No Model")
            ui.print_tool_result(module.name, False, f"找不到 {task.role.value} 模型")
            return
        
        task.status = TaskStatus.IN_PROGRESS
        self._update_todo_item(module.name, task.status)
        if monitor:
            monitor.update_task(module.name, "Starting...")
        console.print(f"[cyan]╭─ {module.name} ({task.role.value}) ─{'─' * (30 - len(module.name))}[/cyan]")
        
        interface_info = self._build_interface_info(module)
        
        tech_stack_instruction = ""
        if self.architecture and self.architecture.tech_stack:
            tech_stack_instruction = f"统一技术栈/风格要求: {self.architecture.tech_stack}\n请严格遵守此要求。"

        if self.domain == "content":
            prompt = f"""撰写以下章节。

用户需求: {user_request}
你的任务: {module.description}
章节名: {module.name}
要点: {module.interface}
{tech_stack_instruction}

上下文:
{context}

要求:
1. 确保内容风格统一
2. 遵循大纲结构
3. 使用 write_file 将内容保存为 Markdown 文件 ({module.name}.md)

请使用工具完成创作。"""

            messages = [
                Message(role=Role.SYSTEM, content=f"你是专业内容创作者，角色是 {task.role.value}。负责撰写 {module.name}。"),
                Message(role=Role.USER, content=prompt)
            ]
        else:
            prompt = f"""实现以下模块。

用户需求: {user_request}
你的任务: {module.description}
模块名: {module.name}
接口定义: {module.interface}
{tech_stack_instruction}

依赖接口:
{interface_info}

上下文:
{context}

要求:
1. 实现完整的代码
2. 遵循接口定义
3. 使用工具读取/写入文件
4. 如果遇到困难，可以请求其他模型帮助

请使用工具完成代码实现。"""

            messages = [
                Message(role=Role.SYSTEM, content=f"你是 {task.role.value} 模型，负责实现 {module.name} 模块。你可以使用所有工具。"),
                Message(role=Role.USER, content=prompt)
            ]
        
        tools = self.tool_registry.get_all_definitions()
        
        max_iterations = 15
        tool_calls_count = 0
        
        for i in range(max_iterations):
            step_msg = f"Step {i+1}/{max_iterations}"
            console.print(f"[dim]│[/dim] {step_msg}...", end="\r")
            if monitor:
                monitor.update_task(module.name, step_msg)
            
            response = await self._call_agent_with_tools(
                agent, 
                messages, 
                tools, 
                use_live_stream=False,
                monitor=monitor,
                task_name=module.name
            )
            messages.append(response)
            
            if response.content and response.content.startswith("Error:"):
                console.print(f"[red]│ {response.content}[/red]")
            
            if not response.tool_calls:
                if "[REQUEST_HELP" in response.content:
                    console.print(f"[magenta]│ 请求帮助...[/magenta]")
                    if monitor:
                        monitor.update_task(module.name, "Requesting Help")
                    help_result = await self._handle_help_request(task, response.content, context)
                    if help_result:
                        messages.append(Message(role=Role.USER, content=f"帮助结果: {help_result}"))
                        continue
                
                task.code_output = response.content
                task.status = TaskStatus.COMPLETED
                task.result = f"{module.name} 实现完成"
                self._update_todo_item(module.name, task.status)
                console.print(f"[cyan]╰─ [green]✓[/green] {module.name} 完成 ({tool_calls_count} 次工具调用)[/cyan]")
                if monitor:
                    monitor.update_task(module.name, "Completed")
                return
            
            for tool_call in response.tool_calls:
                tool_calls_count += 1
                tool = self.tool_registry.get(tool_call.name)
                if tool:
                    console.print(f"[dim]│ {tool_call.name}...[/dim]")
                    if monitor:
                        monitor.update_task(module.name, f"Tool: {tool_call.name}")
                    try:
                        result = await tool.execute(tool_call.arguments, self.working_dir)
                        status = "[green]✓[/green]" if result.success else "[red]✗[/red]"
                        console.print(f"[dim]│ {tool_call.name} {status}[/dim]")
                        messages.append(Message(
                            role=Role.TOOL,
                            content=result.output if result.success else result.error,
                            tool_call_id=tool_call.id,
                        ))
                    except Exception as e:
                        console.print(f"[dim]│ {tool_call.name} [red]✗[/red] {e}[/dim]")
                        messages.append(Message(
                            role=Role.TOOL,
                            content=f"工具执行错误: {e}",
                            tool_call_id=tool_call.id,
                        ))
        
        task.status = TaskStatus.FAILED
        self._update_todo_item(module.name, task.status)
        task.issues.append("达到最大迭代次数")
        console.print(f"[cyan]╰─ [red]✗[/red] {module.name} 失败 (达到最大迭代次数)[/cyan]")
        if monitor:
            monitor.update_task(module.name, "Failed (Max Steps)")
    
    async def _repair_module(
        self,
        task: ParallelTask,
        module: ModuleSpec,
        user_request: str,
        context: str,
    ):
        """Repair a failed module using Opus."""
        opus = self.agents.get(ModelRole.OPUS)
        if not opus:
            opus = self.agents.get(ModelRole.PRO)
        if not opus:
            return
        
        console.print(f"[yellow]╭─ 修复 {module.name} ─{'─' * (30 - len(module.name))}[/yellow]")
        
        prompt = f"""修复以下失败的模块。

用户需求: {user_request}
模块名: {module.name}
模块描述: {module.description}
接口定义: {module.interface}

之前的错误:
{chr(10).join(task.issues) if task.issues else '达到最大迭代次数'}

上下文:
{context}

请使用工具直接创建这个模块需要的所有文件。不要解释，直接写代码！"""

        messages = [
            Message(role=Role.SYSTEM, content="你是专家，负责修复失败的模块。直接使用工具创建文件，不要废话。"),
            Message(role=Role.USER, content=prompt)
        ]
        
        tools = self.tool_registry.get_all_definitions()
        
        max_iterations = 10
        for i in range(max_iterations):
            console.print(f"[dim]│ 等待响应 ({i+1}/{max_iterations})...[/dim]", end="\r")
            response = await self._call_agent_with_tools(opus, messages, tools)
            messages.append(response)
            
            if response.content and response.content.startswith("Error:"):
                console.print(f"[red]│ {response.content}[/red]")
            
            if not response.tool_calls:
                task.code_output = response.content
                task.status = TaskStatus.COMPLETED
                console.print(f"[yellow]╰─ [green]✓[/green] {module.name} 修复成功[/yellow]")
                return
            
            for tool_call in response.tool_calls:
                tool = self.tool_registry.get(tool_call.name)
                if tool:
                    ui.print_tool_start(tool_call.name, tool_call.arguments)
                    try:
                        result = await tool.execute(tool_call.arguments, self.working_dir)
                        ui.print_tool_output(result.output if result.success else str(result.error), result.success)
                        messages.append(Message(
                            role=Role.TOOL,
                            content=result.output if result.success else result.error,
                            tool_call_id=tool_call.id,
                        ))
                    except Exception as e:
                        ui.print_tool_output(f"错误: {e}", False)
                        messages.append(Message(
                            role=Role.TOOL,
                            content=f"错误: {e}",
                            tool_call_id=tool_call.id,
                        ))
        
        console.print(f"[yellow]╰─ [red]✗[/red] {module.name} 修复失败[/yellow]")
    
    async def _handle_help_request(
        self,
        task: ParallelTask,
        content: str,
        context: str,
    ) -> Optional[str]:
        """Handle dynamic help request between models."""
        # Parse help request
        match = re.search(r'\[REQUEST_HELP:\s*(\w+)\s*\](.*?)(?=\[|$)', content, re.DOTALL)
        if not match:
            return None
        
        helper_role_str = match.group(1).lower()
        help_content = match.group(2).strip()
        
        # Map role name
        role_map = {
            "fast": ModelRole.FAST,
            "pro": ModelRole.PRO,
            "sonnet": ModelRole.SONNET,
            "opus": ModelRole.OPUS,
        }
        
        helper_role = role_map.get(helper_role_str)
        if not helper_role:
            return None
        
        helper = self.agents.get(helper_role)
        if not helper:
            return f"请求的 {helper_role_str} 模型不可用"
        
        console.print(f"[yellow]  {task.role.value} 请求 {helper_role.value} 帮助...[/yellow]")
        
        prompt = f"""你的同事在实现模块时遇到了困难，请帮助解决。

求助内容: {help_content}

上下文: {context}

请提供具体的解决方案或代码建议。"""

        messages = [
            Message(role=Role.SYSTEM, content=f"你是 {helper_role.value} 模型，正在帮助同事解决问题。"),
            Message(role=Role.USER, content=prompt)
        ]
        
        response = await self._call_agent(helper, messages, use_live_stream=False)
        return response
    
    async def _integrate_modules(
        self,
        user_request: str,
        context: str,
    ) -> str:
        """Opus integrates all modules."""
        opus = self.agents.get(ModelRole.OPUS)
        if not opus:
            opus = list(self.agents.values())[0] if self.agents else None
        
        if not opus:
            return "没有可用的整合模型"
        
        failed_modules = []
        for task in self.tasks.values():
            if task.status != TaskStatus.COMPLETED:
                module = self._find_module_by_task(task)
                if module:
                    failed_modules.append(module)
        
        if failed_modules:
            console.print(f"[yellow]发现 {len(failed_modules)} 个失败模块，尝试修复...[/yellow]")
            
            for module in failed_modules:
                task = self._find_task_by_module_name(module.name)
                if task:
                    console.print(f"[cyan]重新实现 {module.name}...[/cyan]")
                    await self._repair_module(task, module, user_request, context)
        
        module_outputs = []
        for task in self.tasks.values():
            module = self._find_module_by_task(task)
            if module:
                status_icon = "✓" if task.status == TaskStatus.COMPLETED else "✗"
                module_outputs.append(f"""
=== {module.name} {status_icon} ===
描述: {module.description}
接口: {module.interface}
实现状态: {task.status.value}
代码片段 (前 500 字符):
{task.code_output[:500] if task.code_output else "(无输出)"}
...
""")
        
        tech_stack_instruction = ""
        if self.architecture and self.architecture.tech_stack:
            tech_stack_instruction = f"\n统一风格/技术栈: {self.architecture.tech_stack}"

        if self.domain == "content":
             prompt = f"""整合所有章节，生成完整的内容文档。
        
用户需求: {user_request}
{tech_stack_instruction}

各章节摘要:
{''.join(module_outputs)}

要求:
1. 读取所有章节文件 ({module.name}.md)
2. 将它们合并为一个完整的文档 (如 final_content.md)
3. 添加必要的过渡、目录和引言
4. 确保格式统一
5. 删除临时的章节文件

请生成最终文档。"""
        else:
            prompt = f"""整合所有模块，生成完整的可运行代码。
        
用户需求: {user_request}
{tech_stack_instruction}

各模块实现摘要:
{''.join(module_outputs)}

接口定义:
{json.dumps(self.architecture.interfaces if self.architecture else {}, indent=2)}

要求:
1. 检查各模块是否已创建文件（使用 list_directory 和 read_file）
2. 如果文件已存在，验证其内容并进行必要的修改以确保接口兼容
3. 如果文件不存在，根据代码片段和接口定义创建文件
4. 修复任何冲突
5. 生成使用说明
6. 确保最终产物符合统一技术栈要求，删除不相关的文件。

重要：必须确保所有必要的文件都存在且内容正确！"""

        messages = [
            Message(role=Role.SYSTEM, content=f"你是 Opus 模型，负责整合所有工作成果。当前领域: {self.domain}"),
            Message(role=Role.USER, content=prompt)
        ]
        
        tools = self.tool_registry.get_all_definitions()
        
        stream_buffer: list[str] = []
        text_widget = Text("")
        
        try:
            max_iterations = 30
            for i in range(max_iterations):
                console.print(f"[dim]  整合: 等待模型响应 ({i+1}/{max_iterations})...[/dim]", end="\r")
                response = await self._call_agent_with_tools(opus, messages, tools)
                messages.append(response)
                
                if response.content and response.content.startswith("Error:"):
                    console.print(f"[red]  整合: {response.content}[/red]")
                
                if response.content:
                    stream_buffer.append(response.content)
                
                if not response.tool_calls:
                    break
                
                for tool_call in response.tool_calls:
                    tool = self.tool_registry.get(tool_call.name)
                    if tool:
                        ui.print_tool_start(tool_call.name, tool_call.arguments)
                        try:
                            result = await tool.execute(tool_call.arguments, self.working_dir)
                            ui.print_tool_output(result.output if result.success else str(result.error), result.success)
                            messages.append(Message(
                                role=Role.TOOL,
                                content=result.output if result.success else result.error,
                                tool_call_id=tool_call.id,
                            ))
                        except Exception as e:
                            ui.print_tool_output(f"错误: {e}", False)
                            messages.append(Message(
                                role=Role.TOOL,
                                content=f"错误: {e}",
                                tool_call_id=tool_call.id,
                            ))
        except Exception as e:
            console.print(f"[red]整合过程出错: {e}[/red]")
        
        final_content = "".join(stream_buffer)
        
        summary_prompt = f"""基于以下整合过程，生成简洁的完成报告。

整合输出:
{final_content[:3000]}

请生成:
1. 完成的功能概述
2. 主要文件列表（列出实际创建的文件）
3. 使用说明"""

        messages = [
            Message(role=Role.USER, content=summary_prompt)
        ]
        
        summary = await self._call_agent(opus, messages)
        return summary
    
    def _build_interface_info(self, module: ModuleSpec) -> str:
        """Build interface info from dependencies."""
        # Find modules this module depends on
        info = []
        
        for task in self.tasks.values():
            if task.status == TaskStatus.COMPLETED and task.code_output:
                other_module = self._find_module_by_task(task)
                if other_module and other_module.name != module.name:
                    info.append(f"\n{other_module.name} 接口:\n{other_module.interface}")
                    info.append(f"实现:\n{task.code_output[:1000]}...")
        
        return "\n".join(info) if info else "无依赖"
    
    def _find_task_by_module_name(self, name: str) -> Optional[ParallelTask]:
        for i, module in enumerate(self.architecture.modules if self.architecture else []):
            if module.name == name:
                return self.tasks.get(f"module_{i}")
        return None
    
    def _find_module_by_name(self, name: str) -> Optional[ModuleSpec]:
        for module in self.architecture.modules if self.architecture else []:
            if module.name == name:
                return module
        return None
    
    def _find_module_by_task(self, task: ParallelTask) -> Optional[ModuleSpec]:
        idx = int(task.id.replace("module_", ""))
        if self.architecture and idx < len(self.architecture.modules):
            return self.architecture.modules[idx]
        return None
    
    async def _call_agent(
        self, 
        agent: Any, 
        messages: list[Message], 
        timeout: int = 600, 
        use_live_stream: bool = True,
        task_name: str = ""
    ) -> str:
        """Call agent without tools."""
        stats.record_call(role=agent.role.value if hasattr(agent, 'role') else 'unknown')
        
        try:
            if use_live_stream:
                with ui.create_live_session() as session:
                    response = await agent.client.chat_stream(
                        messages=messages,
                        tools=[],
                        max_tokens=4096,
                        temperature=0.7,
                        on_content=lambda c: session.update_content(c),
                        on_thinking=lambda t: session.update_thinking(t),
                    )
                return response.content or ""
            else:
                # Use stream even without UI to handle timeouts better and show activity
                content_buffer = []
                last_log_time = 0
                
                def on_content(chunk):
                    content_buffer.append(chunk)
                    nonlocal last_log_time
                    import time
                    current_time = time.time()
                    if current_time - last_log_time > 5 and task_name:
                        console.print(f"[dim]  {task_name}: generating... ({len(''.join(content_buffer))} chars)[/dim]", end="\r")
                        last_log_time = current_time

                response = await asyncio.wait_for(
                    agent.client.chat_stream(
                        messages=messages,
                        tools=[],
                        max_tokens=4096,
                        temperature=0.7,
                        on_content=on_content,
                    ),
                    timeout=timeout
                )
                if task_name:
                    console.print(f"[dim]  {task_name}: completed ({len(response.content or '')} chars)[/dim]")
                return response.content or ""
        except asyncio.TimeoutError:
            return f"Error: API调用超时 ({timeout}秒)"
        except Exception as e:
            return f"Error: {e}"
    
    async def _call_agent_with_tools(
        self,
        agent: Any,
        messages: list[Message],
        tools: list,
        timeout: int = 600,
        use_live_stream: bool = True,
        monitor: Any = None,
        task_name: str = "",
    ) -> Message:
        """Call agent with tool support."""
        stats.record_call(role=agent.role.value if hasattr(agent, 'role') else 'unknown')
        
        try:
            if use_live_stream:
                # ... (live stream logic) ...
                with ui.create_live_session() as session:
                    def on_tool_update(name, args):
                        session.update_tool(name, args)
                        
                    response = await agent.client.chat_stream(
                        messages=messages,
                        tools=tools,
                        max_tokens=4096,
                        temperature=0.7,
                        on_content=lambda c: session.update_content(c),
                        on_thinking=lambda t: session.update_thinking(t),
                        on_tool_update=on_tool_update,
                    )
                return response
            else:
                # Use stream even without UI to handle timeouts better and show activity
                content_buffer = []
                last_log_time = 0
                
                def on_content(chunk):
                    content_buffer.append(chunk)
                    nonlocal last_log_time
                    import time
                    current_time = time.time()
                    if current_time - last_log_time > 2 and task_name:  # Update more frequently for monitor
                        msg = f"Generating... ({len(''.join(content_buffer))} chars)"
                        if monitor:
                            monitor.update_task(task_name, msg)
                        else:
                            console.print(f"[dim]  {task_name}: {msg}[/dim]", end="\r")
                        last_log_time = current_time
                
                def on_tool_update(name, args):
                    msg = f"Calling tool: {name}"
                    if monitor:
                        monitor.update_task(task_name, msg)
                        monitor.add_log(f"{task_name}: {msg}")
                    elif task_name:
                        console.print(f"[dim]  {task_name}: {msg}[/dim]")

                response = await asyncio.wait_for(
                    agent.client.chat_stream(
                        messages=messages,
                        tools=tools,
                        max_tokens=4096,
                        temperature=0.7,
                        on_content=on_content,
                        on_tool_update=on_tool_update,
                    ),
                    timeout=timeout
                )
                
                final_msg = f"Completed ({len(response.content or '')} chars)"
                if monitor:
                    monitor.update_task(task_name, "Completed")
                    monitor.add_log(f"{task_name}: {final_msg}")
                elif task_name:
                    console.print(f"[dim]  {task_name}: {final_msg}[/dim]")
                    
                return response
        except asyncio.TimeoutError:
            return Message(role=Role.ASSISTANT, content=f"Error: API调用超时 ({timeout}秒)")
        except Exception as e:
            return Message(role=Role.ASSISTANT, content=f"Error: {e}")
