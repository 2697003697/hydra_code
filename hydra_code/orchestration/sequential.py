from typing import Any, Optional
from rich.console import Console
from rich.panel import Panel

from ..clients import Message, Role
from .roles import ModelRole
from ..tools import ToolRegistry
from .. import ui

from ..todo import TodoList, TaskStatus
from ..ui import TodoListRenderer

console = Console()

class SequentialCollaborator:
    """
    Manages sequential execution for maintenance and modification tasks.
    Uses a Planner -> Executor workflow instead of parallel architecture.
    """
    
    def __init__(
        self,
        agents: dict[ModelRole, Any],
        tool_registry: ToolRegistry,
        working_dir: str,
        domain: str = "coding",
    ):
        self.agents = agents
        self.tool_registry = tool_registry
        self.working_dir = working_dir
        self.domain = domain
        self.todo_list = TodoList(title="Maintenance Plan")

    async def execute(self, user_request: str, context: str) -> str:
        """Execute the sequential maintenance workflow."""
        
        # 1. Analysis & Planning
        plan = await self._create_plan(user_request, context)
        
        # 2. Execution
        result = await self._execute_plan(plan, user_request, context)
        
        return result

    async def _create_plan(self, user_request: str, context: str) -> str:
        """
        Step 1: Analyze the request and create a step-by-step plan.
        Uses FAST or PRO model.
        """
        ui.print_phase("计划生成", "分析现有代码并制定修改计划...")
        
        pro_agent = self.agents.get(ModelRole.PRO) or self.agents.get(ModelRole.FAST)
        if not pro_agent:
            return "No planner available."

        prompt = f"""你是 Pro 模型，负责规划维护任务。

用户需求: {user_request}

当前上下文摘要:
{context}

任务类型: {self.domain} (维护/修改)

你的目标:
分析需求并为开发者创建一个清晰的、分步执行的计划。
确定需要读取、修改或创建哪些文件。

请按以下格式输出计划 (务必包含 TODO 列表):

1. 分析: [简要分析]
2. 文件: [相关文件]
3. 步骤 (TODO List):
   TODO: [步骤 1 内容]
   TODO: [步骤 2 内容]
   ...

保持简洁和可执行性。
"""
        messages = [
            Message(role=Role.USER, content=prompt)
        ]
        
        response = await self._call_agent(pro_agent, messages)
        console.print(Panel(response, title="Modification Plan", border_style="blue"))
        
        # Parse Todo List
        self._parse_plan_to_todo(response)
        if self.todo_list.items:
            console.print(TodoListRenderer(self.todo_list))
            
        return response

    def _parse_plan_to_todo(self, plan: str):
        self.todo_list.clear()
        for line in plan.splitlines():
            clean_line = line.strip()
            if clean_line.startswith("TODO:") or clean_line.startswith("- TODO:"):
                content = clean_line.split("TODO:", 1)[1].strip()
                self.todo_list.add_task(content)


    async def _execute_plan(self, plan: str, user_request: str, context: str) -> str:
        """
        Step 2: Execute the plan using a strong model (SONNET/OPUS) with tools.
        """
        ui.print_phase("执行修改", "正在执行修改计划...")
        
        sonnet_agent = self.agents.get(ModelRole.SONNET) or self.agents.get(ModelRole.OPUS) or self.agents.get(ModelRole.PRO)
        
        if not sonnet_agent:
            return "No executor available."

        system_prompt = f"""你是 Sonnet 模型，负责执行维护计划。
你的任务是执行以下维护计划。

用户需求: {user_request}

计划:
{plan}

你可以完全访问文件系统工具。
1. 首先读取必要的文件以理解上下文。
2. 使用 `search_replace` 或 `write_file` 应用更改。
3. 尽可能验证你的更改。

上下文:
{context}

请一步步执行。
"""
        
        messages = [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content="请开始执行计划。")
        ]
        
        tools = self.tool_registry.get_all_definitions()
        
        final_response = ""
        max_turns = 15
        
        from ..ui import LiveStreamSession
        
        async with LiveStreamSession(title="Executing Plan...") as session:
            for i in range(max_turns):
                session.update_status(f"Turn {i+1}/{max_turns}")
                
                # Call Agent
                response_msg = await self._call_agent_with_tools(sonnet_agent, messages, tools, session)
                messages.append(response_msg)
                
                if response_msg.content:
                    final_response = response_msg.content
                
                if not response_msg.tool_calls:
                    # If no tool calls and we have a response, we might be done
                    if "done" in response_msg.content.lower() or "completed" in response_msg.content.lower():
                        break
                    # Stop if no tools after 5 turns
                    if i > 5:
                        break
                
                # Execute Tools
                if response_msg.tool_calls:
                    for tool_call in response_msg.tool_calls:
                        tool = self.tool_registry.get(tool_call.name)
                        if tool:
                            session.update_tool_status(tool_call.name, "Running", tool_call.arguments)
                            try:
                                result = await tool.execute(tool_call.arguments, self.working_dir)
                                output = result.output if result.success else f"Error: {result.error}"
                                session.update_tool_status(tool_call.name, "Done" if result.success else "Failed")
                                
                                messages.append(Message(
                                    role=Role.TOOL,
                                    content=output,
                                    tool_call_id=tool_call.id
                                ))
                            except Exception as e:
                                messages.append(Message(
                                    role=Role.TOOL,
                                    content=f"Execution Error: {str(e)}",
                                    tool_call_id=tool_call.id
                                ))

        return final_response

    async def _call_agent(self, agent: Any, messages: list[Message]) -> str:
        """Helper to call agent without tools (for planning)."""
        response = await agent.chat(messages)
        return response.content

    async def _call_agent_with_tools(self, agent: Any, messages: list[Message], tools: list[dict], session: Any) -> Message:
        """Helper to call agent with streaming."""
        
        def on_tool_update(name, args):
            session.update_tool_status(name, "Calling", args)
            
        response = await agent.chat_stream(
            messages=messages,
            tools=tools,
            on_content=lambda c: session.update_content(c),
            on_thinking=lambda t: session.update_thinking(t),
            on_tool_update=on_tool_update,
        )
            
        return response
