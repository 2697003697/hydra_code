"""
Leader-Worker collaboration mode.
A designated Leader model manages the entire process, delegating tasks to Worker models.
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
from rich.markdown import Markdown

from .roles import ModelRole
from .state import CollaborationState
from ..clients import Message, Role, ToolDefinition
from ..tools import ToolRegistry
from ..ui import ui

console = Console()


@dataclass
class SubTask:
    id: str
    description: str
    assigned_to: ModelRole
    status: str = "pending"  # pending, assigned, completed, failed, reviewed
    result: str = ""
    feedback: str = ""


class LeaderCollaborator:
    """
    Implements the Leader-Worker pattern.
    The Leader model (default: Opus) plans, delegates, and reviews work.
    """

    def __init__(
        self,
        agents: dict[ModelRole, Any],
        tool_registry: ToolRegistry,
        working_dir: str,
        leader_role: ModelRole = ModelRole.OPUS,
    ):
        self.agents = agents
        self.tool_registry = tool_registry
        self.working_dir = working_dir
        self.leader_role = leader_role
        self.workers = {r: a for r, a in agents.items() if r != leader_role}
        self.tasks: dict[str, SubTask] = {}
        self.state: Optional[CollaborationState] = None
        self.max_steps = 15

    def set_leader(self, leader_role: ModelRole):
        """Update the leader role and reassign workers."""
        target_role = leader_role
        
        # Ensure we're using a key that exists in agents
        if target_role not in self.agents:
             # If exact match not found, try string match or fallback
             found = False
             for r in self.agents.keys():
                 if r.value == leader_role.value:
                     target_role = r
                     found = True
                     break
             if not found:
                 console.print(f"[yellow]Warning: Leader role {leader_role.value} not found in agents. Keeping {self.leader_role.value}[/yellow]")
                 return

        self.leader_role = target_role
        self.workers = {r: a for r, a in self.agents.items() if r != target_role}
        console.print(f"[dim]Leader switched to {target_role.value}. Workers: {', '.join([r.value for r in self.workers.keys()])}[/dim]")

    async def execute(self, user_request: str, context: str = "", domain: str = "coding", intent: str = "new", complexity: str = "complex") -> str:
        """Execute the Leader-Worker workflow."""
        self.state = CollaborationState(user_request, self.working_dir)
        
        ui.print_phase("Leader Mode", f"Leader ({self.leader_role.value}) 正在统筹全局 (领域: {domain}, 意图: {intent}, 复杂度: {complexity})")
        
        leader_agent = self.agents.get(self.leader_role)
        if not leader_agent:
            # Fallback if specific leader not found
            if self.agents:
                # Try to find best fallback: Opus -> Sonnet -> Pro -> Fast
                fallback_order = [ModelRole.OPUS, ModelRole.SONNET, ModelRole.PRO, ModelRole.FAST]
                found = False
                for role in fallback_order:
                    if role in self.agents:
                        self.leader_role = role
                        leader_agent = self.agents[role]
                        found = True
                        break
                
                if not found:
                    self.leader_role = next(iter(self.agents.keys()))
                    leader_agent = self.agents[self.leader_role]

                ui.print_phase("Leader Mode", f"Fallback to Leader ({self.leader_role.value})")
            else:
                return f"Error: No models available."

        # System prompt for the Leader
        domain_instruction = ""
        if domain == "content":
            domain_instruction = "当前任务是内容创作/文档编写，请侧重于结构清晰、语言优美。"
        elif domain == "general":
            domain_instruction = "当前任务是通用问答，请直接回答问题，必要时调用工具验证。"
        else:
            domain_instruction = "当前任务是软件开发，请严格遵守代码规范，确保代码可运行。"

        intent_instruction = ""
        if intent == "new":
            intent_instruction = "用户意图是【新建】，请从头开始设计和实现，确保架构合理。"
        elif intent == "modify":
            intent_instruction = "用户意图是【修改】，请先理解现有代码，只修改必要部分，保持风格一致。"
        elif intent == "qa":
            intent_instruction = "用户意图是【问答/咨询】，请提供准确、详尽的解答，必要时进行验证。"
        else:
            intent_instruction = f"用户意图是【{intent}】，请灵活应对。"

        complexity_instruction = ""
        if complexity == "simple":
            complexity_instruction = "当前任务较简单，请快速完成，避免过度设计。"
        elif complexity == "moderate":
            complexity_instruction = "当前任务为中等复杂度，请注意代码结构，确保修改的稳健性。"
        elif complexity == "complex":
            complexity_instruction = "当前任务较为复杂，请先制定详细计划，分步骤执行，充分利用 Worker 的能力。"
        else:
            complexity_instruction = ""

        system_prompt = f"""你是团队的 Leader ({self.leader_role.value})。
        你负责完成用户请求："{user_request}"。

        任务领域: {domain}
        {domain_instruction}

        任务意图: {intent}
        {intent_instruction}

        任务复杂度: {complexity}
        {complexity_instruction}

        你有以下下属 (Workers) 可供调遣：
{', '.join([f"{r.value}" for r in self.workers.keys()])}

你的职责：
1. 分析任务，决定是自己做还是分派给 Worker。
2. 如果分派任务，请明确任务描述和验收标准。
3. 审查 Worker 的提交结果。
4. 整合所有成果，向用户汇报。

可用工具：
- 标准文件/命令工具 (read_file, write_file, run_command 等)
- 任务分派工具 (delegate_task)
- 任务审查工具 (review_task)

当前上下文：
{context}

请一步步思考并行动。
如果任务已完成，请直接回复"任务完成"并总结。
"""

        messages = [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=f"任务开始。请分析需求并制定计划。")
        ]

        # Prepare tools
        tools = self.tool_registry.get_all_definitions()
        
        # Add special tools for Leader
        delegate_tool = ToolDefinition(
            name="delegate_task",
            description="Delegate a subtask to a worker model.",
            parameters={
                "type": "object",
                "properties": {
                    "worker_role": {
                        "type": "string",
                        "enum": [r.value for r in self.workers.keys()],
                        "description": "The role of the worker to assign the task to."
                    },
                    "task_description": {
                        "type": "string",
                        "description": "Detailed description of the task."
                    }
                },
                "required": ["worker_role", "task_description"]
            }
        )
        
        review_tool = ToolDefinition(
            name="review_task",
            description="Review the result of a completed subtask.",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The ID of the task to review."
                    },
                    "approved": {
                        "type": "boolean",
                        "description": "Whether the task result is approved."
                    },
                    "feedback": {
                        "type": "string",
                        "description": "Feedback for the worker (if rejected) or comments (if approved)."
                    }
                },
                "required": ["task_id", "approved"]
            }
        )
        
        tools.extend([delegate_tool, review_tool])

        step = 0
        while step < self.max_steps:
            step += 1
            console.print(f"\n[bold cyan]Leader Round {step}[/bold cyan]")
            
            # Leader thinks and acts
            try:
                response = await self._call_agent(leader_agent, messages, tools)
            except Exception as e:
                console.print(f"[red]Leader error: {e}[/red]")
                break
                
            messages.append(response)
            
            if not response.tool_calls:
                # If Leader just talks, check if it's the final answer
                content_lower = (response.content or "").lower()
                if "任务完成" in content_lower or "task completed" in content_lower:
                    return response.content or "任务完成"
                continue

            # Handle Tool Calls
            for tool_call in response.tool_calls:
                tool_name = tool_call.name
                args = tool_call.arguments
                
                result_content = ""
                
                if tool_name == "delegate_task":
                    worker_role_str = args.get("worker_role")
                    task_desc = args.get("task_description")
                    
                    try:
                        # Handle case-insensitive role matching
                        worker_role = None
                        for r in ModelRole:
                            if r.value == worker_role_str:
                                worker_role = r
                                break
                        if not worker_role:
                            # Fallback try to find by name
                            for r in ModelRole:
                                if r.name.lower() == str(worker_role_str).lower():
                                    worker_role = r
                                    break
                                    
                        if worker_role:
                            task_id = f"task_{len(self.tasks) + 1}"
                            self.tasks[task_id] = SubTask(task_id, task_desc, worker_role)
                            
                            ui.print_phase("Delegation", f"Leader 分派任务给 {worker_role.value}: {task_desc[:50]}...")
                            
                            # Execute Worker Task immediately (synchronous for now, can be async)
                            worker_result = await self._execute_worker_task(task_id)
                            result_content = f"Task {task_id} assigned to {worker_role.value}.\nExecution Result:\n{worker_result}"
                        else:
                            result_content = f"Error: Invalid worker role {worker_role_str}"
                        
                    except Exception as e:
                        result_content = f"Error in delegation: {e}"

                elif tool_name == "review_task":
                    task_id = args.get("task_id")
                    approved = args.get("approved")
                    feedback = args.get("feedback", "")
                    
                    if task_id in self.tasks:
                        task = self.tasks[task_id]
                        task.status = "reviewed" if approved else "failed"
                        task.feedback = feedback
                        status_str = "Approved" if approved else "Rejected"
                        ui.print_phase("Review", f"Leader 审查 {task_id}: {status_str}. Feedback: {feedback}")
                        result_content = f"Task {task_id} marked as {status_str}."
                    else:
                        result_content = f"Error: Task {task_id} not found."

                else:
                    # Standard tools
                    tool = self.tool_registry.get(tool_name)
                    if tool:
                        ui.print_tool_start(tool_name, args)
                        res = await tool.execute(args, self.working_dir)
                        ui.print_tool_output(res.output if res.success else str(res.error), res.success)
                        result_content = res.output if res.success else f"Error: {res.error}"
                    else:
                        result_content = f"Error: Unknown tool {tool_name}"

                messages.append(Message(
                    role=Role.TOOL,
                    content=result_content,
                    tool_call_id=tool_call.id
                ))

        return "Leader execution reached max steps."

    async def _execute_worker_task(self, task_id: str) -> str:
        """Execute a task assigned to a worker."""
        task = self.tasks[task_id]
        worker_agent = self.agents.get(task.assigned_to)
        
        if not worker_agent:
            return "Error: Worker agent not found."
            
        console.print(f"[dim]Worker {task.assigned_to.value} starting task: {task.description}[/dim]")
        
        system_prompt = f"""你是 {task.assigned_to.value}。
Leader 分配给你一个任务：
{task.description}

请使用工具完成任务，并详细汇报结果。
"""
        messages = [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content="开始执行任务。")
        ]
        
        tools = self.tool_registry.get_all_definitions()
        
        # Simple worker loop (simplified)
        for i in range(5):
            try:
                response = await self._call_agent(worker_agent, messages, tools)
            except Exception as e:
                return f"Worker error: {e}"
                
            messages.append(response)
            
            if not response.tool_calls:
                task.result = response.content
                task.status = "completed"
                return response.content or "Task completed (no content)"
                
            for tool_call in response.tool_calls:
                tool = self.tool_registry.get(tool_call.name)
                if tool:
                    ui.print_tool_start(tool_call.name, tool_call.arguments)
                    res = await tool.execute(tool_call.arguments, self.working_dir)
                    ui.print_tool_output(res.output if res.success else str(res.error), res.success)
                    tool_content = res.output if res.success else str(res.error)
                    if len(tool_content) > 8000:
                        tool_content = tool_content[:8000] + "\n... [内容已截断]"
                    messages.append(Message(role=Role.TOOL, content=tool_content, tool_call_id=tool_call.id))
                else:
                    messages.append(Message(role=Role.TOOL, content=f"Error: Unknown tool {tool_call.name}", tool_call_id=tool_call.id))
        
        return "Worker max steps reached."

    async def _call_agent(self, agent: Any, messages: list[Message], tools: list[ToolDefinition] = None) -> Message:
        """Helper to call agent with live streaming."""
        client = agent.client if hasattr(agent, 'client') else agent
        role_name = agent.role.value if hasattr(agent, 'role') else "Assistant"
        
        try:
            with ui.create_live_session() as session:
                response = await client.chat_stream(
                    messages=messages,
                    tools=tools,
                    temperature=0.7,
                    on_content=lambda c: session.update_content(c),
                    on_thinking=lambda t: session.update_thinking(t),
                )
            return response
        except Exception as e:
            console.print(f"[red]Agent {role_name} error: {e}[/red]")
            return Message(role=Role.ASSISTANT, content=f"Error: {e}")
