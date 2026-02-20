"""
Task dispatcher for analyzing and distributing tasks to appropriate models.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .roles import ModelRole, get_role_definition


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

    def analyze(self, user_input: str, context: Optional[dict] = None) -> TaskAnalysis:
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
