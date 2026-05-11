"""
Dynamic collaboration coordinator with structured planning.
Implements a workflow: Quick Routing → Planning → Parallel Execution → Validation → Summary.
"""

import asyncio
import re
import time
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum

from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich.panel import Panel
from rich.columns import Columns

from .roles import ModelRole, get_role_definition, get_role_by_name
from .communication import Discovery
from .state import CollaborationState, SharedContext
from .parallel import ParallelCollaborator
from .sequential import SequentialCollaborator
from .leader import LeaderCollaborator
from ..clients import Message, Role, ToolDefinition, create_client
from ..config import Config
from ..tools import ToolRegistry, get_default_tools
from .. import stats
from ..ui import ui

console = Console()


class WorkflowPhase(Enum):
    QUICK_ROUTING = "quick_routing"
    PLANNING = "planning"
    EXECUTING = "executing"
    COLLABORATING = "collaborating"
    VALIDATING = "validating"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"


class TaskComplexity(Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


@dataclass
class TaskStep:
    id: int
    description: str
    status: str = "pending"
    result: str = ""
    issues: list[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    steps: list[TaskStep]
    current_step: int = 0
    
    def get_current_step(self) -> Optional[TaskStep]:
        if self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None
    
    def advance(self):
        self.current_step += 1
    
    def is_complete(self) -> bool:
        return self.current_step >= len(self.steps)
    
    def get_progress(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == "completed")
        return completed / len(self.steps) * 100
    
    def mark_current_step_completed(self, result: str = "", issues: list[str] = None):
        step = self.get_current_step()
        if step:
            step.status = "completed"
            step.result = result
            if issues:
                step.issues = issues
            self.advance()


@dataclass
class ModelAgent:
    role: ModelRole
    model_name: str
    client: Any
    is_busy: bool = False
    max_tokens: Optional[int] = None


ROUTING_PROMPT = """你是 Fast 模型，负责判断用户请求的复杂度和任务类型：

用户请求: {user_input}

- complexity:
  - simple: 简单任务（问答、单个文件、小游戏等）
  - moderate: 中等任务（多步修改、小型功能开发）
  - complex: 复杂任务（大型项目、架构设计、全栈开发）

- domain:
  - coding: 编程任务（代码、软件、工具、Debug）
  - content: 内容创作（文章、报告、策划、翻译、分析）
  - general: 通用问题（逻辑推理、常识问答）

- intent:
  - new: 从头创建新项目/新文件/新内容 (Greenfield)
  - modify: 修改/更新/重构现有内容 (Brownfield, e.g. "update readme", "fix bug")
  - qa: 纯问答/解释

仅输出一行合法JSON，禁止任何解释、问候语或Markdown代码块。必须直接以{{开头，以}}结尾：
{{"complexity": "simple/moderate/complex", "domain": "coding/content/general", "intent": "new/modify/qa", "reason": "理由"}}
"""


PLANNING_PROMPT = """你是 Pro 模型，负责制定高层次的任务计划。

## 用户请求
{user_request}

## 项目上下文
{context}

请制定高层次的任务计划。每个步骤应该是一个有意义的任务单元，而不是具体的文件操作。

例如：
- "修复认证模块的token验证问题" ✓
- "更新路由中间件配置" ✓
- "添加错误处理机制" ✓
- "读取文件" ✗ (太具体)
- "写入代码" ✗ (太具体)

输出 JSON 数组格式：
```json
[
  {{"step": 1, "description": "修复认证模块的token验证问题"}},
  {{"step": 2, "description": "更新路由中间件配置"}},
  ...
]
```

注意：
1. 每个步骤应该是一个完整的、有意义的任务
2. 步骤之间有逻辑依赖关系
3. 不要太细碎，每个步骤可以包含多个文件操作
"""


COLLABORATION_PROMPT = """你们是 Pro 和 Sonnet 模型，需要合作完成以下任务。

## 任务描述
{task_description}

## 项目上下文
{context}

## 已完成的工作
{completed_work}

## 遇到的问题
{issues}

请合作完成这个任务：

1. Sonnet 先分析问题，确定需要修改哪些文件
2. Pro 根据分析结果编写代码
3. Sonnet 验证代码是否正确

输出 JSON 格式：
{{
  "analysis": "问题分析",
  "files_to_modify": ["文件1", "文件2"],
  "changes": [
    {{"file": "文件路径", "action": "create/edit", "content": "完整内容或修改描述"}}
  ],
  "validation": "验证结果",
  "success": true/false,
  "issues": ["问题1", "问题2"],
  "next_actions": ["下一步建议"]
}}
"""


OPUS_HELP_PROMPT = """你是 Opus 模型，拥有最强的能力，需要帮助解决 Pro 和 Sonnet 无法解决的问题。

## 当前任务
{task_description}

## Pro 和 Sonnet 的工作
{work_done}

## 他们遇到的问题
{issues}

## 项目上下文
{context}

请按以下步骤处理：

### 第一步：问题诊断
明确指出问题的根本原因，不要模糊描述。

### 第二步：解决方案
给出具体的、可执行的解决方案。

### 第三步：执行修改
提供需要修改的文件内容。

输出 JSON 格式：
{{
  "problem_diagnosis": {{
    "root_cause": "问题的根本原因",
    "affected_files": ["受影响的文件列表"],
    "error_type": "错误类型（如：语法错误、逻辑错误、配置错误等）"
  }},
  "solution": {{
    "description": "解决方案描述",
    "steps": ["步骤1", "步骤2", "步骤3"]
  }},
  "changes": [
    {{"file": "文件路径", "action": "create/edit", "content": "完整内容"}}
  ],
  "success": true/false,
  "message": "给用户的说明信息"
}}
"""


FINAL_VALIDATION_PROMPT = """你是 Opus 模型，负责最终验证整体工作成果。

## 用户原始请求
{user_request}

## 任务计划
{plan}

## 完成的工作
{completed_work}

## 项目上下文
{context}

请按以下步骤验证：

### 第一步：功能验证
检查所有功能是否按要求实现。

### 第二步：代码质量验证
检查代码是否有语法错误、逻辑错误。

### 第三步：运行验证
检查代码是否可以正常运行。

如果发现问题，必须明确指出：
1. 具体哪个文件有问题
2. 问题是什么
3. 如何修复

输出 JSON 格式：
{{
  "validation_result": {{
    "all_tasks_completed": true/false,
    "code_quality_ok": true/false,
    "can_run": true/false
  }},
  "issues": [
    {{
      "file": "文件路径",
      "problem": "具体问题描述",
      "solution": "修复方案",
      "severity": "critical/warning/info"
    }}
  ],
  "completed": true/false,
  "need_restart": true/false,
  "restart_from_step": 1,
  "message": "给用户的验证结果说明"
}}
"""


SUMMARY_PROMPT = """你是 Pro 模型，负责生成最终报告。

## 用户原始请求
{user_request}

## 任务计划
{plan}

## 完成的工作
{completed_work}

请生成一份清晰的中文报告，包括：
1. 任务概述
2. 完成的工作
3. 创建/修改的文件列表
4. 使用说明（如有）
5. 注意事项（如有）
"""


@dataclass
class RoutingResult:
    complexity: TaskComplexity
    domain: str
    intent: str
    reason: str


def _extract_json(text: str) -> Optional[str]:
    m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    if m:
        return m.group(1)
    depth = 0
    start = -1
    for i, c in enumerate(text):
        if c == '{':
            if depth == 0:
                start = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start:i+1]
    return None


class DynamicCoordinator:
    def __init__(self, config: Config, working_dir: str, work_history: Any = None):
        self.config = config
        self.working_dir = working_dir
        self.work_history = work_history
        self.agents: dict[ModelRole, ModelAgent] = {}
        self.state: Optional[CollaborationState] = None
        self.plan: Optional[ExecutionPlan] = None
        self.phase = WorkflowPhase.QUICK_ROUTING
        self.tool_registry = ToolRegistry()
        self.start_time: float = 0
        self.max_time_seconds: int = 600
        self.step_results: dict[int, str] = {}
        self.all_issues: list[str] = []
        self._workspace_context: str = ""
        self._smart_context = None
        self.force_mode: Optional[str] = None
        
        self._setup_tools()
        self._setup_agents()
    
    def _setup_tools(self):
        for tool in get_default_tools():
            self.tool_registry.register(tool)
    
    def _setup_agents(self):
        for role in ModelRole:
            api_key, base_url, model_name, provider, max_tokens = self.config.get_role_config(role.value)
            
            if api_key and base_url and model_name:
                client = create_client(
                    api_key=api_key,
                    base_url=base_url,
                    model_name=model_name,
                    provider=provider,
                )
                self.agents[role] = ModelAgent(
                    role=role,
                    model_name=model_name,
                    client=client,
                    max_tokens=max_tokens,
                )

    async def _analyze_request(self, text: str) -> RoutingResult:
        """Analyze user request complexity and intent using Fast or Pro."""
        routing_agent = self._get_agent_with_fallback([ModelRole.FAST, ModelRole.PRO])
        
        if not routing_agent:
            return RoutingResult(TaskComplexity.SIMPLE, "coding", "new", "No routing agent")
        
        prompt = ROUTING_PROMPT.format(user_input=text)
        messages = [Message(role=Role.USER, content=prompt)]
        
        try:
            response = await self._call_agent(routing_agent, messages, max_tokens=300)

            json_match = _extract_json(response)

            # If Fast fails to output JSON, try Pro if available
            if not json_match and routing_agent.role == ModelRole.FAST and ModelRole.PRO in self.agents:
                console.print("[dim]Fast模型分析失败，尝试使用Pro模型...[/dim]")
                pro_agent = self.agents[ModelRole.PRO]
                response = await self._call_agent(pro_agent, messages, max_tokens=300)
                json_match = _extract_json(response)

            if json_match:
                result = json.loads(json_match)
                complexity_str = result.get("complexity", "simple")
                domain = result.get("domain", "coding")
                intent = result.get("intent", "new")
                reason = result.get("reason", "")
                
                console.print(f"[dim]路由分析: {complexity_str} / {domain} / {intent} - {reason}[/dim]")
                
                try:
                    complexity = TaskComplexity(complexity_str)
                except ValueError:
                    complexity = TaskComplexity.SIMPLE
                    
                return RoutingResult(complexity, domain, intent, reason)
        except Exception as e:
            console.print(f"[yellow]路由分析失败: {e}[/yellow]")
            
        return RoutingResult(TaskComplexity.SIMPLE, "coding", "new", "Analysis failed")
    
    def _is_timeout(self) -> bool:
        if self.start_time == 0:
            return False
        return (time.time() - self.start_time) > self.max_time_seconds
    
    def set_force_mode(self, mode: Optional[str]):
        self.force_mode = mode
        if mode:
            console.print(f"[cyan]已强制设置为 {mode} 模式[/cyan]")
        else:
            console.print(f"[cyan]已取消强制模式[/cyan]")
    
    async def collaborate(
        self,
        user_request: str,
        on_update: Optional[Callable[[str], None]] = None,
        memory_context: str = "",
    ) -> str:
        """
        Main entry point for collaboration.
        """
        stats.reset_stats()
        self.start_time = time.time()
        self.state = CollaborationState(user_request, self.working_dir)
        self.step_results = {}
        self.all_issues = []
        
        ui.print_thinking("扫描工作区...")
        await self._scan_workspace()
        ui.clear_thinking()

        # 1. Force Mode Handling
        if self.force_mode:
            # Explicit Leader Mode
            if self.force_mode.startswith("leader"):
                # Parse optional role: "leader:sonnet" or just "leader"
                parts = self.force_mode.split(":")
                leader_role_name = parts[1] if len(parts) > 1 else "opus"
                
                # Try to map string to ModelRole, default to Opus
                try:
                    # Try direct match first
                    target_role = ModelRole(leader_role_name)
                except ValueError:
                    # Try to find by value or name
                    target_role = ModelRole.OPUS
                    for r in ModelRole:
                        if r.value == leader_role_name:
                            target_role = r
                            break

                ui.print_phase("启动协作", f"强制 Leader 模式 (Leader: {target_role.value})")
                
                collaborator = LeaderCollaborator(
                    agents=self.agents,
                    tool_registry=self.tool_registry,
                    working_dir=self.working_dir,
                    leader_role=target_role
                )
                return await collaborator.execute(
                    user_request, 
                    self._workspace_context, 
                    domain="coding", 
                    intent="unknown", 
                    complexity="complex"
                )

            # Explicit Parallel Mode (Legacy)
            elif self.force_mode == "parallel":
                ui.print_phase("启动协作", "强制并行模式 (无 Leader)")
                collaborator = ParallelCollaborator(
                    agents={r: a.client for r, a in self.agents.items()},
                    tool_registry=self.tool_registry,
                    working_dir=self.working_dir,
                    domain="coding"
                )
                return await collaborator.execute(user_request, self._workspace_context)

        # 2. Auto Routing (Standard Path)
        ui.print_phase("分析请求", "正在分析任务复杂度...")
        routing = await self._analyze_request(user_request)
        
        # Simple Path -> Single Model
        if routing.complexity == TaskComplexity.SIMPLE:
            ui.print_phase("快速响应", f"检测到简单任务 ({routing.domain})")
            return await self._quick_response(user_request, memory_context)
        
        # Moderate/Complex Path -> Leader Mode
        complexity_desc = "中等" if routing.complexity == TaskComplexity.MODERATE else "复杂"
        ui.print_phase("启动协作", f"检测到{complexity_desc}任务 ({routing.domain})，启动 Leader 协作模式")
        
        # Default to Opus as leader for auto mode, fallback to others
        leader_agent = self._get_agent_with_fallback([ModelRole.OPUS, ModelRole.SONNET, ModelRole.PRO])
        leader_role = leader_agent.role if leader_agent else ModelRole.OPUS
        
        collaborator = LeaderCollaborator(
            agents=self.agents,
            tool_registry=self.tool_registry,
            working_dir=self.working_dir,
            leader_role=leader_role
        )
        
        result = await collaborator.execute(
            user_request, 
            self._workspace_context, 
            domain=routing.domain,
            intent=routing.intent,
            complexity=routing.complexity.value
        )
        self._show_stats()
        return result
    
    def _show_stats(self):
        s = stats.get_stats()
        if s.total_calls > 0:
            ui.print_stats({
                "API调用次数": s.total_calls,
                "按角色": ", ".join(f"{k}: {v}次" for k, v in s.calls_by_role.items()),
            })
    
    def _get_agent_with_fallback(self, preferred_roles: list[ModelRole]) -> Any:
        """Get the first available agent from a list of preferred roles."""
        for role in preferred_roles:
            if role in self.agents:
                return self.agents[role]
        
        # Fallback to any available agent
        if self.agents:
            fallback = next(iter(self.agents.values()))
            # console.print(f"[dim]Fallback to {fallback.role.value}[/dim]")
            return fallback
        return None

    async def _quick_response(self, question: str, memory_context: str = "") -> str:
        # Simple task priority: Fast (Speed) -> Sonnet (Balance) -> Opus (Power)
        agent = self._get_agent_with_fallback([ModelRole.FAST, ModelRole.SONNET, ModelRole.OPUS])

        if not agent:
            return "没有可用的模型来回答问题"

        context = self._get_project_context()

        system_prompt = f"""你是一个AI代码助手，可以帮助用户完成软件工程任务。

你可以使用以下工具：
- read_file: 读取文件内容
- write_file: 写入文件
- edit_file: 编辑文件
- list_directory: 列出目录
- search_files: 搜索文件
- run_command: 执行命令
- search_code: 搜索代码
- download_file: 下载工作目录内文件

当前工作目录: {self.working_dir}

{context}

{memory_context}
"""
        
        messages = [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=question)
        ]
        
        tools = self.tool_registry.get_all_definitions()
        
        max_iterations = 10
        for i in range(max_iterations):
            response = await self._call_agent_with_tools(agent, messages, tools)
            messages.append(response)
            
            if not response.tool_calls:
                return response.content
            
            # ui.print_thinking(f"执行工具 ({i+1}/{max_iterations})")
            
            for tool_call in response.tool_calls:
                tool = self.tool_registry.get(tool_call.name)
                if not tool:
                    messages.append(Message(
                        role=Role.TOOL,
                        content=f"Unknown tool: {tool_call.name}",
                        tool_call_id=tool_call.id,
                    ))
                    continue
                
                ui.print_tool_start(tool_call.name, tool_call.arguments)
                
                result = await tool.execute(tool_call.arguments, self.working_dir)
                
                ui.print_tool_output(result.output if result.success else str(result.error), result.success)
                
                if result.success:
                    if tool_call.name == "write_file":
                        if self.work_history:
                            self.work_history.add_file_created(tool_call.arguments.get("file_path", ""))
                    elif tool_call.name == "edit_file":
                        if self.work_history:
                            self.work_history.add_file_modified(tool_call.arguments.get("file_path", ""))
                
                tool_result_content = result.output if result.success else f"Error: {result.error}"
                if len(tool_result_content) > 8000:
                    tool_result_content = tool_result_content[:8000] + "\n... [内容已截断]"
                messages.append(Message(
                    role=Role.TOOL,
                    content=tool_result_content,
                    tool_call_id=tool_call.id,
                ))
        
        return "已达到最大迭代次数"
    
    async def _scan_workspace(self) -> str:
        from ..codebase import get_smart_context
        from pathlib import Path
        
        try:
            self._smart_context = get_smart_context(
                root_path=Path(self.working_dir),
                work_history=self.work_history,
            )
            self._workspace_context = self._smart_context.get_lightweight_context()
            return self._workspace_context
        except Exception as e:
            console.print(f"[yellow]扫描工作区失败: {e}[/yellow]")
            tool = self.tool_registry.get("list_directory")
            if tool:
                result = await tool.execute({"path": "."}, self.working_dir)
                if result.success:
                    self._workspace_context = result.output[:2000]
                    return self._workspace_context
        return ""
    
    def _get_project_context(self) -> str:
        if hasattr(self, '_smart_context') and self._smart_context:
            return self._smart_context.get_full_context(max_size=60000)
        
        context_parts = []
        context_parts.append(f"工作目录: {self.working_dir}")
        
        if self._workspace_context:
            context_parts.append(f"\n## 目录结构\n```\n{self._workspace_context}\n```")
        
        if self.work_history:
            history_summary = self.work_history.get_summary()
            if history_summary:
                context_parts.append(f"\n## 工作历史\n{history_summary}")
        
        return "\n".join(context_parts)
    
    async def _call_agent_with_tools(self, agent: Any, messages: list[Message], tools: list[ToolDefinition] = None) -> Message:
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
                    on_tool_call=lambda t, a: session.update_tool(t, a)
                )
            return response
        except Exception as e:
            console.print(f"[red]Agent {role_name} error: {e}[/red]")
            return Message(role=Role.ASSISTANT, content=f"Error: {e}")
    
    async def _call_agent(self, agent: ModelAgent, messages: list[Message], max_tokens: int = None) -> str:
        tokens = max_tokens or agent.max_tokens or self.config.max_tokens
        stats.record_call(role=agent.role.value)
        
        try:
            with ui.create_live_session() as session:
                response = await agent.client.chat_stream(
                    messages=messages,
                    tools=[],
                    max_tokens=tokens,
                    temperature=self.config.temperature,
                    on_content=lambda c: session.update_content(c),
                    on_thinking=lambda t: session.update_thinking(t),
                )
            
            return response.content or ""
            
        except Exception as e:
            console.print(f"[red]Agent {agent.role.value} error: {e}[/red]")
            return f"Error: {e}"
    
    def get_status(self) -> dict:
        return {
            "phase": self.phase.value,
            "elapsed_time": time.time() - self.start_time if self.start_time else 0,
            "plan_progress": self.plan.get_progress() if self.plan else 0,
            "current_step": self.plan.current_step + 1 if self.plan else 0,
            "total_steps": len(self.plan.steps) if self.plan else 0,
            "issues": len(self.all_issues),
            "agents": [
                {
                    "role": a.role.value,
                    "model": a.model_name,
                    "busy": a.is_busy,
                }
                for a in self.agents.values()
            ],
        }
