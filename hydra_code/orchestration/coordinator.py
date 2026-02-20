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
from ..clients import Message, Role, create_client
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
  - complex: 复杂任务（项目、多文件、长篇文章等）

- domain:
  - coding: 编程任务（代码、软件、工具、Debug）
  - content: 内容创作（文章、报告、策划、翻译、分析）
  - general: 通用问题（逻辑推理、常识问答）

- intent:
  - new: 从头创建新项目/新文件/新内容 (Greenfield)
  - modify: 修改/更新/重构现有内容 (Brownfield, e.g. "update readme", "fix bug")
  - qa: 纯问答/解释

回复JSON：
{{"complexity": "simple/complex", "domain": "coding/content/general", "intent": "new/modify/qa", "reason": "理由"}}
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
        fast_agent = self.agents.get(ModelRole.FAST)
        if not fast_agent:
            fast_agent = next(iter(self.agents.values())) if self.agents else None
        
        if not fast_agent:
            return RoutingResult(TaskComplexity.SIMPLE, "coding", "new", "No fast_agent")
        
        prompt = ROUTING_PROMPT.format(user_input=text)
        messages = [Message(role=Role.USER, content=prompt)]
        
        try:
            response = await self._call_agent(fast_agent, messages, max_tokens=150)
            
            json_match = re.search(r'\{[\s\S]+\}', response)
            if json_match:
                result = json.loads(json_match.group())
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
    ) -> str:
        stats.reset_stats()
        self.start_time = time.time()
        self.state = CollaborationState(user_request, self.working_dir)
        self.step_results = {}
        self.all_issues = []
        
        ui.print_thinking("扫描工作区...")
        await self._scan_workspace()
        ui.clear_thinking()
        
        # New Routing Logic
        ui.print_thinking("分析任务领域与复杂度...")
        routing = await self._analyze_request(user_request)
        ui.clear_thinking()
        
        if self.force_mode == "simple":
            return await self._quick_response(user_request)
        elif self.force_mode == "complex":
            # Force complex but use detected domain if available, default to coding
            domain = routing.domain if routing else "coding"
            return await self._full_workflow(user_request, domain)
            
        if routing.complexity == TaskComplexity.SIMPLE:
            self.phase = WorkflowPhase.QUICK_ROUTING
            result = await self._quick_response(user_request)
            self._show_stats()
            return result
        
        # Complex Path
        if routing.intent == "modify":
            # Use Sequential Maintenance Workflow
            ui.print_phase("启动维护", f"检测到维护/更新任务 ({routing.domain})，启动顺序维护模式")
            
            collaborator = SequentialCollaborator(
                agents={r: a.client for r, a in self.agents.items()},
                tool_registry=self.tool_registry,
                working_dir=self.working_dir,
                domain=routing.domain
            )
            return await collaborator.execute(user_request, self._workspace_context)
        else:
            # Use Parallel Creation Workflow
            result = await self._full_workflow(user_request, routing.domain)
            self._show_stats()
            return result
    
    def _show_stats(self):
        s = stats.get_stats()
        if s.total_calls > 0:
            ui.print_stats({
                "API调用次数": s.total_calls,
                "按角色": ", ".join(f"{k}: {v}次" for k, v in s.calls_by_role.items()),
            })
    
    async def _quick_response(self, question: str) -> str:
        opus_agent = self.agents.get(ModelRole.OPUS)
        if not opus_agent:
            opus_agent = self.agents.get(ModelRole.FAST)
        if not opus_agent:
            opus_agent = next(iter(self.agents.values())) if self.agents else None
        
        if not opus_agent:
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

当前工作目录: {self.working_dir}

{context}
"""
        
        messages = [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=question)
        ]
        
        tools = self.tool_registry.get_all_definitions()
        
        max_iterations = 10
        for i in range(max_iterations):
            response = await self._call_agent_with_tools(opus_agent, messages, tools)
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
                messages.append(Message(
                    role=Role.TOOL,
                    content=tool_result_content,
                    tool_call_id=tool_call.id,
                ))
        
        return "已达到最大迭代次数"
    
    async def _full_workflow(self, user_request: str, domain: str = "coding") -> str:
        """Execute the full complex workflow."""
        self.phase = WorkflowPhase.PLANNING
        
        ui.print_phase("启动协作", f"检测到复杂任务 ({domain})，启动多模型协作模式")
        
        collaborator = ParallelCollaborator(
            agents={r: a.client for r, a in self.agents.items()},
            tool_registry=self.tool_registry,
            working_dir=self.working_dir,
            domain=domain
        )
        
        return await collaborator.execute(user_request, self._workspace_context)
    
    async def _create_plan(self, user_request: str) -> list[dict]:
        pro_agent = self.agents.get(ModelRole.PRO)
        if not pro_agent:
            pro_agent = self.agents.get(ModelRole.OPUS)
        
        if not pro_agent:
            return []
        
        context = self._get_project_context()
        
        prompt = PLANNING_PROMPT.format(
            user_request=user_request,
            context=context,
        )
        
        messages = [Message(role=Role.USER, content=prompt)]
        response = await self._call_agent(pro_agent, messages)
        
        try:
            json_match = re.search(r'\[[\s\S]*?\]', response)
            if json_match:
                plan = json.loads(json_match.group())
                if isinstance(plan, list):
                    return [{"step": s.get("step", i+1), "description": s.get("description", "")} 
                            for i, s in enumerate(plan)]
        except json.JSONDecodeError:
            pass
        
        return []
    
    async def _execute_task_with_collaboration(self, task: TaskStep, user_request: str) -> dict:
        max_attempts = 3
        attempt = 0
        issues = []
        
        while attempt < max_attempts:
            attempt += 1
            
            console.print(f"[dim]  Sonnet + Pro 协作执行 (尝试 {attempt}/{max_attempts})[/dim]")
            
            result = await self._pro_sonnet_collaborate(task, user_request, issues)
            
            if result.get("success"):
                if self.work_history:
                    self.work_history.add_task(task.description, result.get("validation", "完成"), True)
                return {
                    "success": True,
                    "result": result.get("validation", "完成"),
                    "issues": []
                }
            
            issues = result.get("issues", [])
            
            if issues and attempt < max_attempts:
                console.print(f"[yellow]  发现问题，尝试自行解决...[/yellow]")
                continue
            
            console.print(f"[magenta]  Sonnet 和 Pro 无法解决，请求 Opus 帮助...[/magenta]")
            
            opus_result = await self._opus_help(task, user_request, result, issues)
            
            if opus_result.get("success"):
                if self.work_history:
                    solution_data = opus_result.get("solution", {})
                    if isinstance(solution_data, dict):
                        solution_text = solution_data.get("description", "Opus 已解决")
                    else:
                        solution_text = str(solution_data) if solution_data else "Opus 已解决"
                    self.work_history.add_task(task.description, solution_text, True)
                return {
                    "success": True,
                    "result": opus_result.get("message", "Opus 已解决"),
                    "issues": []
                }
            
            issues_raw = opus_result.get("issues", [])
            if isinstance(issues_raw, list):
                issues = []
                for issue in issues_raw:
                    if isinstance(issue, dict):
                        issues.append(f"{issue.get('file', '')}: {issue.get('problem', str(issue))}")
                    else:
                        issues.append(str(issue))
            else:
                issues = issues_raw if issues_raw else issues
        
        if self.work_history:
            self.work_history.add_task(task.description, "失败", False)
        return {
            "success": False,
            "result": "多次尝试后仍失败",
            "issues": issues
        }
    
    async def _pro_sonnet_collaborate(self, task: TaskStep, user_request: str, previous_issues: list[str]) -> dict:
        sonnet_agent = self.agents.get(ModelRole.SONNET)
        pro_agent = self.agents.get(ModelRole.PRO)
        
        if not sonnet_agent or not pro_agent:
            return {"success": False, "issues": ["缺少 Sonnet 或 Pro"]}
        
        context = self._get_project_context()
        completed_work = self._get_completed_work_summary()
        issues_str = "\n".join(previous_issues) if previous_issues else "无"
        
        prompt = COLLABORATION_PROMPT.format(
            task_description=task.description,
            context=context,
            completed_work=completed_work,
            issues=issues_str,
        )
        
        messages = [Message(role=Role.USER, content=prompt)]
        response = await self._call_agent(pro_agent, messages, max_tokens=4000)
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                
                analysis = result.get("analysis", "")
                files_to_modify = result.get("files_to_modify", [])
                validation = result.get("validation", "")
                
                if analysis:
                    console.print(f"[dim]  分析: {analysis[:150]}...[/dim]")
                
                if files_to_modify:
                    console.print(f"[dim]  目标文件: {', '.join(files_to_modify[:5])}[/dim]")
                
                changes = result.get("changes", [])
                for change in changes:
                    await self._apply_change(change)
                
                if validation:
                    console.print(f"[dim]  验证: {validation[:100]}...[/dim]")
                
                return result
        except json.JSONDecodeError:
            pass
        
        return {"success": False, "issues": ["无法解析协作结果"]}
    
    async def _opus_help(self, task: TaskStep, user_request: str, work_done: dict, issues: list[str]) -> dict:
        opus_agent = self.agents.get(ModelRole.OPUS)
        if not opus_agent:
            return {"success": False, "issues": ["Opus 不可用"]}
        
        context = self._get_project_context()
        work_str = json.dumps(work_done, ensure_ascii=False, indent=2)
        issues_str = "\n".join(issues) if issues else "无"
        
        prompt = OPUS_HELP_PROMPT.format(
            task_description=task.description,
            work_done=work_str,
            issues=issues_str,
            context=context,
        )
        
        messages = [Message(role=Role.USER, content=prompt)]
        response = await self._call_agent(opus_agent, messages, max_tokens=4000)
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                
                diagnosis = result.get("problem_diagnosis", {})
                solution = result.get("solution", {})
                message = result.get("message", "")
                
                if diagnosis:
                    console.print(f"\n[yellow]╭─ 问题诊断 ─{'─' * 40}[/yellow]")
                    root_cause = diagnosis.get("root_cause", "")
                    affected_files = diagnosis.get("affected_files", [])
                    error_type = diagnosis.get("error_type", "")
                    
                    if root_cause:
                        console.print(f"[yellow]│[/yellow] [red]根本原因:[/red] {root_cause}")
                    if error_type:
                        console.print(f"[yellow]│[/yellow] [red]错误类型:[/red] {error_type}")
                    if affected_files:
                        console.print(f"[yellow]│[/yellow] [red]受影响文件:[/red] {', '.join(affected_files)}")
                    console.print(f"[yellow]╰──────────────────────────────────────────────[/yellow]")
                
                if solution:
                    console.print(f"\n[green]╭─ 解决方案 ─{'─' * 40}[/green]")
                    description = solution.get("description", "")
                    steps = solution.get("steps", [])
                    
                    if description:
                        console.print(f"[green]│[/green] 方案: {description}")
                    if steps:
                        console.print("[green]│[/green] 执行步骤:")
                        for i, step in enumerate(steps, 1):
                            console.print(f"[green]│[/green]   {i}. {step}")
                    console.print(f"[green]╰──────────────────────────────────────────────[/green]")
                
                if message:
                    console.print(f"\n[cyan]说明: {message}[/cyan]")
                
                changes = result.get("changes", [])
                for change in changes:
                    await self._apply_change(change)
                
                return result
        except json.JSONDecodeError:
            pass
        
        return {"success": False, "issues": ["Opus 无法解析"]}
    
    async def _apply_change(self, change: dict):
        action = change.get("action", "")
        file_path = change.get("file", "")
        content = change.get("content", "")
        
        if not file_path or not content:
            return
        
        if action == "create":
            tool = self.tool_registry.get("write_file")
            if tool:
                result = await tool.execute({"file_path": file_path, "content": content}, self.working_dir)
                if result.success:
                    ui.print_tool_result("write_file", True, f"创建: {file_path}")
                    if self.work_history:
                        self.work_history.add_file_created(file_path)
                else:
                    ui.print_tool_result("write_file", False, f"创建失败: {file_path}")
        
        elif action == "edit":
            tool = self.tool_registry.get("edit_file")
            if tool:
                read_tool = self.tool_registry.get("read_file")
                existing = ""
                if read_tool:
                    read_result = await read_tool.execute({"file_path": file_path}, self.working_dir)
                    if read_result.success:
                        existing = read_result.output
                
                result = await tool.execute({
                    "file_path": file_path,
                    "old_str": existing[:1000] if existing else "",
                    "new_str": content
                }, self.working_dir)
                
                if result.success:
                    ui.print_tool_result("edit_file", True, f"编辑: {file_path}")
                    if self.work_history:
                        self.work_history.add_file_modified(file_path)
                else:
                    write_tool = self.tool_registry.get("write_file")
                    if write_tool:
                        await write_tool.execute({"file_path": file_path, "content": content}, self.working_dir)
                        ui.print_tool_result("write_file", True, f"覆盖: {file_path}")
                        if self.work_history:
                            self.work_history.add_file_modified(file_path)
    
    async def _final_validation(self, user_request: str) -> dict:
        opus_agent = self.agents.get(ModelRole.OPUS)
        if not opus_agent:
            return {"completed": True, "issues": [], "need_restart": False}
        
        context = self._get_project_context()
        plan_str = "\n".join([f"{s.id}. {s.description} - {s.status}" for s in self.plan.steps])
        completed_str = "\n".join([f"任务 {k}: {v[:300]}" for k, v in self.step_results.items()])
        
        prompt = FINAL_VALIDATION_PROMPT.format(
            user_request=user_request,
            plan=plan_str,
            completed_work=completed_str,
            context=context,
        )
        
        messages = [Message(role=Role.USER, content=prompt)]
        response = await self._call_agent(opus_agent, messages)
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                
                validation = result.get("validation_result", {})
                issues = result.get("issues", [])
                message = result.get("message", "")
                
                console.print(f"\n[cyan]╭─ 验证结果 ─{'─' * 40}[/cyan]")
                
                if validation:
                    all_completed = validation.get("all_tasks_completed", False)
                    code_ok = validation.get("code_quality_ok", False)
                    can_run = validation.get("can_run", False)
                    
                    console.print(f"[cyan]│[/cyan] 功能完成: {'[green]✓[/green]' if all_completed else '[red]✗[/red]'}")
                    console.print(f"[cyan]│[/cyan] 代码质量: {'[green]✓[/green]' if code_ok else '[red]✗[/red]'}")
                    console.print(f"[cyan]│[/cyan] 可运行性: {'[green]✓[/green]' if can_run else '[red]✗[/red]'}")
                
                if issues:
                    console.print(f"[cyan]╰──────────────────────────────────────────────[/cyan]")
                    console.print(f"\n[red]╭─ 发现问题 ─{'─' * 40}[/red]")
                    for issue in issues:
                        file_path = issue.get("file", "")
                        problem = issue.get("problem", "")
                        solution = issue.get("solution", "")
                        severity = issue.get("severity", "warning")
                        
                        severity_color = {
                            "critical": "red",
                            "warning": "yellow",
                            "info": "blue",
                        }.get(severity, "yellow")
                        
                        console.print(f"[red]│[/red] [{severity_color}]● {severity.upper()}[/{severity_color}]")
                        if file_path:
                            console.print(f"[red]│[/red]   文件: {file_path}")
                        if problem:
                            console.print(f"[red]│[/red]   问题: {problem}")
                        if solution:
                            console.print(f"[red]│[/red]   修复: {solution}")
                    
                    console.print(f"[red]╰──────────────────────────────────────────────[/red]")
                
                if message:
                    console.print(f"\n[cyan]说明: {message}[/cyan]")
                
                return result
        except json.JSONDecodeError:
            pass
        
        return {"completed": True, "issues": [], "need_restart": False}
    
    async def _generate_summary(self, user_request: str) -> str:
        pro_agent = self.agents.get(ModelRole.PRO)
        if not pro_agent:
            pro_agent = self.agents.get(ModelRole.OPUS)
        
        if not pro_agent:
            return self._generate_basic_summary()
        
        plan_str = "\n".join([f"{s.id}. {s.description}" for s in self.plan.steps])
        completed_str = "\n".join([f"任务 {k}: {v[:500]}" for k, v in self.step_results.items()])
        
        prompt = SUMMARY_PROMPT.format(
            user_request=user_request,
            plan=plan_str,
            completed_work=completed_str,
        )
        
        messages = [Message(role=Role.USER, content=prompt)]
        return await self._call_agent(pro_agent, messages)
    
    def _generate_basic_summary(self) -> str:
        lines = ["# 任务完成报告", ""]
        lines.append(f"## 任务计划 ({len(self.plan.steps)} 步)")
        
        for step in self.plan.steps:
            status = "✓" if step.status == "completed" else "✗"
            lines.append(f"- {status} 任务 {step.id}: {step.description}")
        
        return "\n".join(lines)
    
    def _get_completed_work_summary(self) -> str:
        if not self.step_results:
            return "无"
        
        lines = []
        for step_id, result in self.step_results.items():
            lines.append(f"任务 {step_id}: {result[:200]}")
        return "\n".join(lines)
    
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
    
    async def _call_agent_with_tools(self, agent: ModelAgent, messages: list[Message], tools: list, max_tokens: int = None) -> Message:
        tokens = max_tokens or self.config.max_tokens
        stats.record_call(role=agent.role.value)
        
        try:
            with ui.create_live_session() as session:
                def on_tool_update(name, args):
                    session.update_tool(name, args)
                    
                response = await agent.client.chat_stream(
                    messages=messages,
                    tools=tools,
                    max_tokens=tokens,
                    temperature=self.config.temperature,
                    on_content=lambda c: session.update_content(c),
                    on_thinking=lambda t: session.update_thinking(t),
                    on_tool_update=on_tool_update,
                )
            return response
            
        except Exception as e:
            console.print(f"[red]Agent {agent.role.value} error: {e}[/red]")
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
            
            return response.content
            
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
