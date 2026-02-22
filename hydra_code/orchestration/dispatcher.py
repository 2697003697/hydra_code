"""
Task dispatcher for analyzing and distributing tasks to appropriate models.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .roles import ModelRole, get_role_definition
from ..clients import Message, Role

DISPATCHER_PROMPT = """你是一个智能任务分发器。请分析用户的请求，并将其拆解为适合不同模型角色的子任务。

可用角色：
- FAST (简单任务，快速响应)
- PRO (代码设计，逻辑规划，复杂任务)
- SONNET (代码编写，Bug修复，具体实现)
- OPUS (复杂推理，文件操作，最终整合，兜底)

任务类型 (task_type)：
- simple: 简单问答，无需复杂上下文
- complex: 需要多步思考或多个文件操作
- multi_stage: 需要串行或并行的多阶段协作

请输出 JSON 格式：
{
  "task_type": "simple/complex/multi_stage",
  "analysis": "简短的任务分析",
  "subtasks": [
    {
      "role": "fast/pro/sonnet/opus",
      "task": "子任务描述",
      "priority": 1-10 (10最高),
      "dependencies": ["依赖的任务描述(可选)"]
    }
  ],
  "direct_response": "如果只是简单问答，直接在此返回回复(可选)"
}

注意：
1. 如果是简单问答，task_type设为simple，subtasks留空或仅分配给FAST。
2. 如果涉及代码修改，通常需要 PRO 设计，SONNET 实现。
3. 如果涉及文件读写，OPUS 比较可靠。
4. 确保子任务描述清晰具体。
"""

class TaskType(Enum):
    SIMPLE = "simple"
    COMPLEX = "complex"
    MULTI_STAGE = "multi_stage"


@dataclass
class SubTask:
    role: ModelRole
    task: str
    priority: int = 0
    dependencies: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskAnalysis:
    task_type: TaskType
    analysis: str
    subtasks: list[SubTask] = field(default_factory=list)
    direct_response: Optional[str] = None


class TaskDispatcher:
    PATTERNS = {
        "simple_qa": [
            r"什么是",
            r"如何(使用|做)",
            r"为什么",
            r"解释(一下)?",
            r"帮我(看看|检查)",
        ],
        "code_generation": [
            r"写(一个|段)",
            r"创建(一个)?",
            r"实现",
            r"编写",
            r"代码",
        ],
        "bug_fix": [
            r"bug",
            r"错误",
            r"问题",
            r"不工作",
            r"报错",
            r"异常",
            r"修复",
        ],
        "algorithm": [
            r"算法",
            r"优化",
            r"复杂度",
            r"性能",
            r"数学",
            r"计算",
        ],
        "architecture": [
            r"架构",
            r"设计",
            r"项目",
            r"系统",
            r"模块",
            r"重构",
        ],
        "file_operation": [
            r"文件",
            r"目录",
            r"读取",
            r"写入",
            r"创建文件",
            r"修改",
        ],
        "chinese_context": [
            r"报告",
            r"文档",
            r"总结",
            r"分析",
            r"方案",
        ],
    }

    def __init__(self):
        self._compiled_patterns = {
            key: [re.compile(p, re.IGNORECASE) for p in patterns]
            for key, patterns in self.PATTERNS.items()
        }

    async def analyze(self, user_input: str, client: Any = None, context: Optional[dict] = None) -> TaskAnalysis:
        # 如果提供了 LLM 客户端，优先使用 LLM 进行智能分析
        if client:
            try:
                return await self._analyze_with_llm(user_input, client, context)
            except Exception as e:
                print(f"智能分发失败，回退到规则匹配: {e}")

        # 回退到基于规则的匹配
        scores = self._classify_intent(user_input)
        task_type = self._determine_task_type(scores, user_input)
        
        if task_type == TaskType.SIMPLE:
            return TaskAnalysis(
                task_type=task_type,
                analysis="简单问答，由 Fast 直接处理",
                direct_response=None,
            )

        subtasks = self._create_subtasks(scores, user_input, context)
        
        return TaskAnalysis(
            task_type=task_type,
            analysis=self._generate_analysis(scores, user_input),
            subtasks=subtasks,
        )

    async def _analyze_with_llm(self, user_input: str, client: Any, context: Optional[dict] = None) -> TaskAnalysis:
        messages = [
            Message(role=Role.SYSTEM, content=DISPATCHER_PROMPT),
            Message(role=Role.USER, content=f"用户请求: {user_input}")
        ]
        
        # 这里的 client 是 ModelClient.client，通常支持 chat_stream 或 chat
        # 假设我们使用 chat_stream 并收集结果，或者如果有直接的 chat 方法
        # 根据 orchestrator.py，client 有 chat_stream
        
        full_response = ""
        # 简单的收集流式响应
        async for chunk in client.chat_stream(messages=messages, tools=[], max_tokens=1000):
             if chunk.content:
                 full_response += chunk.content
        
        return self.parse_dispatcher_response(full_response) or self._fallback_analysis(user_input)

    def _fallback_analysis(self, user_input: str) -> TaskAnalysis:
        # 当 LLM 解析失败时的保底逻辑
        scores = self._classify_intent(user_input)
        task_type = self._determine_task_type(scores, user_input)
        subtasks = self._create_subtasks(scores, user_input)
        return TaskAnalysis(
            task_type=task_type,
            analysis="LLM解析失败，使用规则降级分析",
            subtasks=subtasks
        )

    def _classify_intent(self, text: str) -> dict[str, int]:
        scores = {key: 0 for key in self.PATTERNS}
        
        for key, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    scores[key] += 1
        
        return scores

    def _determine_task_type(self, scores: dict[str, int], text: str) -> TaskType:
        total_score = sum(scores.values())
        
        if total_score <= 1 and len(text) < 100:
            return TaskType.SIMPLE
        
        if scores.get("code_generation", 0) > 0 and scores.get("architecture", 0) > 0:
            return TaskType.MULTI_STAGE
        
        if total_score >= 3:
            return TaskType.COMPLEX
        
        if any(scores.values()):
            return TaskType.COMPLEX
        
        return TaskType.SIMPLE

    def _create_subtasks(
        self, 
        scores: dict[str, int], 
        user_input: str,
        context: Optional[dict] = None
    ) -> list[SubTask]:
        subtasks = []
        
        if scores.get("file_operation", 0) > 0:
            subtasks.append(SubTask(
                role=ModelRole.OPUS,
                task=f"执行文件操作: {user_input}",
                priority=10,
            ))
        
        if scores.get("bug_fix", 0) > 0:
            subtasks.append(SubTask(
                role=ModelRole.SONNET,
                task=f"诊断并修复问题: {user_input}",
                priority=8,
            ))
        
        if scores.get("algorithm", 0) > 0:
            subtasks.append(SubTask(
                role=ModelRole.SONNET,
                task=f"解决算法/优化问题: {user_input}",
                priority=7,
            ))
        
        if scores.get("code_generation", 0) > 0 or scores.get("architecture", 0) > 0:
            subtasks.append(SubTask(
                role=ModelRole.PRO,
                task=f"设计和实现: {user_input}",
                priority=5,
            ))
        
        if scores.get("chinese_context", 0) > 0 and not any(
            r.role == ModelRole.OPUS for r in subtasks
        ):
            subtasks.append(SubTask(
                role=ModelRole.OPUS,
                task=f"生成中文文档/报告: {user_input}",
                priority=3,
            ))
        
        if not subtasks:
            subtasks.append(SubTask(
                role=ModelRole.PRO,
                task=user_input,
                priority=5,
            ))
        
        subtasks.sort(key=lambda x: x.priority, reverse=True)
        return subtasks

    def _generate_analysis(self, scores: dict[str, int], text: str) -> str:
        detected = [k for k, v in scores.items() if v > 0]
        return f"检测到意图类型: {', '.join(detected) if detected else '通用'}"

    def parse_dispatcher_response(self, response: str) -> Optional[TaskAnalysis]:
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                task_type = TaskType(data.get("task_type", "complex"))
                subtasks = []
                
                for st in data.get("subtasks", []):
                    role_str = st.get("role", "pro")
                    try:
                        role = ModelRole(role_str.lower())
                    except ValueError:
                        role = ModelRole.PRO
                    
                    subtasks.append(SubTask(
                        role=role,
                        task=st.get("task", ""),
                        priority=st.get("priority", 5),
                    ))
                
                return TaskAnalysis(
                    task_type=task_type,
                    analysis=data.get("analysis", ""),
                    subtasks=subtasks,
                )
            except (json.JSONDecodeError, KeyError):
                pass
        
        return None
