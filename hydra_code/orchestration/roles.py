"""
Model role definitions for multi-model orchestration.
Each role has specific responsibilities but is not bound to any specific model.
Model-to-role mapping is configured in the config file.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ModelRole(Enum):
    FAST = "fast"
    PRO = "pro"
    SONNET = "sonnet"
    OPUS = "opus"


@dataclass
class RoleDefinition:
    role: ModelRole
    name: str
    description: str
    responsibilities: list[str]
    triggers: list[str]
    system_prompt_suffix: str


ROLE_DEFINITIONS: dict[ModelRole, RoleDefinition] = {
    ModelRole.FAST: RoleDefinition(
        role=ModelRole.FAST,
        name="Fast",
        description="快速响应，任务分类与分发",
        responsibilities=[
            "用户意图快速分类",
            "简单问答直接回复",
            "复杂任务拆解为子任务列表",
            "监控任务进度，超时熔断",
        ],
        triggers=[
            "所有请求的第一入口",
            "简单查询",
            "需要极速响应的场景",
        ],
        system_prompt_suffix="""
你是 Fast 模型，负责：
1. 快速分析用户意图
2. 对于简单问题直接回答
3. 对于复杂任务，将其拆解为子任务并分配给合适的专家模型
4. 监控整体任务进度

回复格式要求：
- 简单问题：直接给出答案
- 复杂任务：使用以下JSON格式输出任务分配
```json
{
  "task_type": "complex",
  "analysis": "任务分析",
  "subtasks": [
    {"role": "pro", "task": "子任务描述"},
    {"role": "sonnet", "task": "子任务描述"}
  ]
}
```
""",
    ),
    ModelRole.PRO: RoleDefinition(
        role=ModelRole.PRO,
        name="Pro",
        description="项目规划与核心代码编写",
        responsibilities=[
            "制定整体项目计划",
            "编写核心业务代码",
            "处理长文档/长上下文分析",
            "统筹其他模型的输出结果",
        ],
        triggers=[
            "涉及全栈开发",
            "长文本分析",
            "多文件协同的任务",
        ],
        system_prompt_suffix="""
你是 Pro 模型，负责：
1. 制定项目整体架构和计划
2. 编写核心业务代码
3. 处理长文档分析
4. 整合其他专家的输出

你需要产出高质量、结构清晰的代码和文档。
""",
    ),
    ModelRole.SONNET: RoleDefinition(
        role=ModelRole.SONNET,
        name="Sonnet",
        description="深度推理与问题解决",
        responsibilities=[
            "解决高难度算法/数学问题",
            "深层Bug诊断与修复",
            "复杂逻辑优化",
            "技术深度分析",
        ],
        triggers=[
            "遇到逻辑死胡同",
            "数学计算",
            "深度推理需求",
        ],
        system_prompt_suffix="""
你是 Sonnet 模型，负责：
1. 解决复杂的算法和数学问题
2. 深度诊断Bug并提供修复方案
3. 优化复杂逻辑
4. 进行技术深度分析

你需要展示详细的推理过程和解决方案。
""",
    ),
    ModelRole.OPUS: RoleDefinition(
        role=ModelRole.OPUS,
        name="Opus",
        description="工具调用与本地操作",
        responsibilities=[
            "执行复杂的本地工具调用",
            "处理高度依赖中文语境的任务",
            "生成符合国内规范的报告/文案",
            "验证其他模型的输出准确性",
        ],
        triggers=[
            "需要调用外部API",
            "复杂操作",
            "中文语境任务",
        ],
        system_prompt_suffix="""
你是 Opus 模型，负责：
1. 执行工具调用和本地操作
2. 处理中文语境任务
3. 生成规范的文档和报告
4. 验证其他模型的输出

你需要确保操作准确执行，输出符合规范。
""",
    ),
}


def get_role_definition(role: ModelRole) -> RoleDefinition:
    return ROLE_DEFINITIONS[role]


def get_role_definitions() -> dict[ModelRole, RoleDefinition]:
    return ROLE_DEFINITIONS


def get_role_by_name(name: str) -> Optional[ModelRole]:
    name_lower = name.lower()
    for role, definition in ROLE_DEFINITIONS.items():
        if role.value == name_lower or definition.name == name:
            return role
    return None
