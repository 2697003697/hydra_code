"""
动态多模型协作的聊天会话管理。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.text import Text

from .clients import Message, Role, ToolCall
from .config import Config
from .codebase import WorkHistory, get_smart_context
from .memory import ConversationMemory, MessageType
from .orchestration import (
    DynamicCoordinator,
    MultiModelOrchestrator,
    ModelRole,
    get_role_definition,
    WorkflowPhase,
)
from .tools import ToolRegistry, get_default_tools
from .ui import ui

console = Console()


SYSTEM_PROMPT = """你是hydra，是一个动态多模型协作的聊天会话管理助手，可以帮助用户完成软件工程任务。

你可以使用以下工具：
- read_file: 读取文件内容 (参数: file_path, offset, limit)
- write_file: 写入文件 (参数: file_path, content) - 必须提供 file_path 和 content
- edit_file: 编辑文件 (参数: file_path, old_content, new_content)
- list_directory: 列出目录 (参数: path)
- search_files: 搜索文件 (参数: pattern)
- run_command: 执行命令 (参数: command)
- search_code: 搜索代码 (参数: query)

重要提示：
1. 打开文件/链接：
   - 如果用户要求"打开"文件（如浏览器查看html）或链接，请使用 run_command 工具。
   - Windows: 使用 start <path> (例如: start index.html)
   - Mac/Linux: 使用 open <path> 或 xdg-open <path>

2. 工具参数校验：
   - write_file: 必须提供 'file_path' 和 'content'。
   - file_path: 必须是完整绝对路径（如 "C:/Users/project/index.html"），不能是目录。
   - 不要使用 'path' 代替 'file_path'，除非工具定义允许。

2. 路径处理：
   - 始终使用正斜杠 '/' 或转义的反斜杠 '\\'。
   - 基于当前工作目录: {working_dir}

3. 代码编辑：
   - 使用 edit_file 进行小范围修改，提供准确的 old_content。
   - 使用 write_file 覆盖整个文件或创建新文件。

{codebase_context}

{memory_context}
"""


@dataclass
class ChatSession:
    config: Config
    working_dir: str
    messages: list[Message] = field(default_factory=list)
    tool_registry: ToolRegistry = field(default_factory=ToolRegistry)
    orchestrator: Optional[MultiModelOrchestrator] = None
    coordinator: Optional[DynamicCoordinator] = None
    use_multi_model: bool = True
    use_dynamic_collaboration: bool = True
    work_history: WorkHistory = field(default_factory=WorkHistory)
    memory: ConversationMemory = field(default_factory=ConversationMemory)

    def __post_init__(self):
        self._setup_tools()
        self._setup_coordinator()
        self._setup_system_prompt()

    def _setup_tools(self):
        for tool in get_default_tools():
            self.tool_registry.register(tool)

    def _setup_coordinator(self):
        # Always try to setup agents for potential single model use
        try:
            self.coordinator = DynamicCoordinator(
                config=self.config,
                working_dir=self.working_dir,
                work_history=self.work_history,
            )
            
            # Store agents reference for single model mode
            self.agents = self.coordinator.agents
            
            available_roles = [r.value for r in self.coordinator.agents.keys()]
            if available_roles:
                console.print(f"[dim]可用模型: {', '.join(available_roles)}[/dim]")
            else:
                console.print("[yellow]无可用模型[/yellow]")
                
        except Exception as e:
            console.print(f"[yellow]协调器初始化失败: {e}[/yellow]")
            self.agents = {}
            
        if self.config.single_model_mode:
            console.print("[dim]单一模型模式已启用[/dim]")
            self.use_dynamic_collaboration = False
            self.use_multi_model = False
            return
        
        # Multi-model mode setup
        if hasattr(self, 'coordinator') and self.coordinator:
            self.use_dynamic_collaboration = True
            self.use_multi_model = True
        else:
            try:
                self.orchestrator = MultiModelOrchestrator(
                    config=self.config,
                    working_dir=self.working_dir,
                )
                self.use_multi_model = True
            except Exception:
                self.use_multi_model = False

    def _setup_system_prompt(self):
        ctx = get_smart_context(Path(self.working_dir))
        context_str = ctx.get_lightweight_context()
        memory_context = self.memory.get_compact_history()

        system_content = SYSTEM_PROMPT.format(
            working_dir=self.working_dir,
            codebase_context=context_str,
            memory_context=memory_context,
        )

        self.messages = [Message(role=Role.SYSTEM, content=system_content)]

    async def process_message(self, user_input: str):
        self.memory.add_message(MessageType.USER, user_input)
        self.messages.append(Message(role=Role.USER, content=user_input))

        # Check if specific single model mode is set
        if hasattr(self, 'single_model_role') and self.single_model_role:
            await self._process_single_model_with_role(user_input, self.single_model_role)
        elif self.use_dynamic_collaboration and self.coordinator:
            await self._process_dynamic_collaboration(user_input)
        elif self.use_multi_model and self.orchestrator:
            await self._process_multi_model(user_input)
        else:
            await self._process_single_model(user_input)

    async def _process_dynamic_collaboration(self, user_input: str):
        console.print("\n[bold blue]Assistant (动态协作):[/bold blue]")
        
        def on_update(status: str):
            pass
        
        result = await self.coordinator.collaborate(user_input, on_update)
        
        console.print()
        console.print(Markdown(result))
        
        self.memory.add_message(MessageType.ASSISTANT, result)
        
        status = self.coordinator.get_status()
        console.print(f"\n[dim]协作完成 - 阶段: {status['phase']}, 耗时: {status['elapsed_time']:.1f}s[/dim]")
        
        stats = self.memory.get_stats()
        console.print(f"[dim]记忆: {stats['message_count']}条消息, ~{stats['total_tokens']}tokens[/dim]")
        
        self.messages.append(Message(
            role=Role.ASSISTANT,
            content=result,
        ))

    async def _process_multi_model(self, user_input: str):
        console.print("\n[bold blue]Assistant (多模型协作):[/bold blue]")
        
        result = await self.orchestrator.process_message(user_input)
        
        if result.success:
            console.print()
            console.print(Markdown(result.content))
            
            self.memory.add_message(MessageType.ASSISTANT, result.content)
            
            if result.summary:
                console.print(f"\n[dim]{result.summary}[/dim]")
            
            self.messages.append(Message(
                role=Role.ASSISTANT,
                content=result.content,
            ))
        else:
            console.print(f"[red]执行失败: {result.content}[/red]")

    async def _process_single_model_with_role(self, user_input: str, role: str):
        from .orchestration import ModelRole
        
        try:
            role_enum = ModelRole(role)
        except ValueError:
            console.print(f"[yellow]Warning: Invalid role '{role}' configured. Falling back to 'fast'.[/yellow]")
            role_enum = ModelRole.FAST

        agent = self.agents.get(role_enum) if hasattr(self, 'agents') else None
        
        if not agent:
            console.print(f"[red]{role.upper()} 模型未配置，请检查配置[/red]")
            return
        
        console.print(f"\n[bold blue]Assistant ({role.upper()}):[/bold blue]")
        
        max_iterations = 20
        for iteration in range(max_iterations):
            stream_buffer: list[str] = []
            
            try:
                with ui.create_live_session() as session:
                    def on_thinking(chunk: str):
                        session.update_thinking(chunk)
                    
                    def on_content(chunk: str):
                        stream_buffer.append(chunk)
                        session.update_content(chunk)

                    def on_tool_update(tool_name: str, args_chunk: str):
                        session.update_tool(tool_name, args_chunk)
                    
                    tools = self.tool_registry.get_all_definitions()
                    compact_messages = self._get_compact_messages()
                    
                    response = await agent.client.chat_stream(
                        messages=compact_messages,
                        tools=tools,
                        max_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                        on_content=on_content,
                        on_thinking=on_thinking,
                        on_tool_update=on_tool_update,
                    )
                
                if stream_buffer:
                    self.memory.add_message(MessageType.ASSISTANT, "".join(stream_buffer))
                
                self.messages.append(response)
                
                if response.tool_calls:
                    await self._process_tool_calls(response.tool_calls)
                else:
                    break
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]操作已取消[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                break
    
    async def _process_single_model(self, user_input: str):
        # In single model mode, use the default role's config
        default_role = self.config.default_role
        await self._process_single_model_with_role(user_input, default_role)

    def _get_compact_messages(self) -> list[Message]:
        if len(self.messages) <= 10:
            return self.messages
        
        system_msg = self.messages[0] if self.messages and self.messages[0].role == Role.SYSTEM else None
        
        recent = self.messages[-8:]
        
        if system_msg:
            return [system_msg] + recent
        return recent

    def _update_live(self, content: str, buffer: list[str], text_widget: Text, live: Live):
        buffer.append(content)
        text_widget.append(content)
        live.update(text_widget)

    async def _process_tool_calls(self, tool_calls: list[ToolCall]):
        for tool_call in tool_calls:
            tool = self.tool_registry.get(tool_call.name)

            if not tool:
                ui.print_error(f"Unknown tool: {tool_call.name}")
                continue

            ui.print_tool_start(tool_call.name, tool_call.arguments)

            if not self.config.auto_approve:
                approved = ui.print_confirm(f"Execute {tool_call.name}?")
                if not approved:
                    console.print("[yellow]Tool execution cancelled[/yellow]")
                    self.messages.append(Message(
                        role=Role.TOOL,
                        content="Tool execution was cancelled by user",
                        tool_call_id=tool_call.id,
                    ))
                    self.memory.add_message(MessageType.TOOL, "Tool cancelled")
                    continue

            if tool_call.name == "write_file":
                file_path = tool_call.arguments.get("file_path", "")
                content = tool_call.arguments.get("content", "")
                if file_path and content:
                    ui.print_code_writing(file_path, content[:1000])
            
            result = await tool.execute(tool_call.arguments, self.working_dir)
            
            if tool_call.name == "write_file":
                self.work_history.add_file_created(tool_call.arguments.get("file_path", ""))
                self.memory.files_created.append(tool_call.arguments.get("file_path", ""))
            elif tool_call.name == "edit_file":
                self.work_history.add_file_modified(tool_call.arguments.get("file_path", ""))
                self.memory.files_modified.append(tool_call.arguments.get("file_path", ""))
            elif tool_call.name == "run_command":
                self.work_history.add_command(tool_call.arguments.get("command", ""))

            ui.print_tool_result(tool_call.name, result.success, 
                                 result.output if result.success else result.error)

            tool_result_content = result.output if result.success else f"Error: {result.error}"
            
            self.memory.add_message(MessageType.TOOL, tool_result_content[:500])

            self.messages.append(Message(
                role=Role.TOOL,
                content=tool_result_content,
                tool_call_id=tool_call.id,
            ))

    def clear_history(self):
        self._setup_system_prompt()
        self.work_history = WorkHistory()
        self.memory.clear()
        if self.coordinator:
            self.coordinator = DynamicCoordinator(
                config=self.config,
                working_dir=self.working_dir,
                work_history=self.work_history,
            )
        if self.orchestrator:
            self.orchestrator.messages = []

    def toggle_multi_model(self):
        self.use_multi_model = not self.use_multi_model
        status = "启用" if self.use_multi_model else "禁用"
        console.print(f"[cyan]多模型协作模式已{status}[/cyan]")

    def toggle_dynamic(self):
        self.use_dynamic_collaboration = not self.use_dynamic_collaboration
        status = "启用" if self.use_dynamic_collaboration else "禁用"
        console.print(f"[cyan]动态协作模式已{status}[/cyan]")

    def get_collaboration_status(self) -> dict:
        if self.coordinator:
            status = self.coordinator.get_status()
            status["memory"] = self.memory.get_stats()
            return status
        return {"status": "unavailable"}

    def show_memory_stats(self):
        stats = self.memory.get_stats()
        console.print(f"\n[cyan]记忆统计[/cyan]")
        console.print(f"  消息数: {stats['message_count']}")
        console.print(f"  估计tokens: {stats['total_tokens']}")
        console.print(f"  摘要数: {stats['summary_count']}")
        console.print(f"  关键决策: {stats['key_decisions']}")
        console.print(f"  创建文件: {stats['files_created']}")
        console.print(f"  修改文件: {stats['files_modified']}")
    
    def set_mode(self, mode: str):
        """
        Set execution mode.
        Modes: fast, pro, sonnet, opus, complex, auto
        """
        from .orchestration import ModelRole
        
        if mode in ["fast", "pro", "sonnet", "opus"]:
            # Single model mode with specific role
            self.config.single_model_mode = True
            self.use_dynamic_collaboration = False
            self.use_multi_model = False
            self.single_model_role = mode
            self.coordinator = None
            self.orchestrator = None
            console.print(f"[green]已切换到 {mode.upper()} 单模型模式[/green]")
            
        elif mode == "complex":
            # Multi-model collaboration mode - FORCE complex workflow
            self.config.single_model_mode = False
            self.use_multi_model = True
            self.use_dynamic_collaboration = True
            self.single_model_role = None
            self._setup_coordinator()
            # Force complex mode in coordinator
            if self.coordinator:
                self.coordinator.set_force_mode("complex")
            console.print("[green]已切换到多模型协作模式（强制）[/green]")
            
        elif mode == "auto":
            # Auto mode - let system decide
            self.config.single_model_mode = False
            self.use_multi_model = True
            self.use_dynamic_collaboration = True
            self.single_model_role = None
            self._setup_coordinator()
            if self.coordinator:
                self.coordinator.set_force_mode(None)
            console.print("[green]已切换到自动判断模式[/green]")
