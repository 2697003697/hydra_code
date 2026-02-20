"""
Result aggregator for combining outputs from multiple models.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from .roles import ModelRole, get_role_definition


@dataclass
class ModelResult:
    role: ModelRole
    success: bool
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    execution_time: float = 0.0


@dataclass
class AggregatedResult:
    success: bool
    content: str
    role_results: dict[ModelRole, ModelResult] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""


class ResultAggregator:
    def __init__(self):
        self.role_order = [
            ModelRole.OPUS,
            ModelRole.SONNET,
            ModelRole.PRO,
            ModelRole.FAST,
        ]

    def aggregate(self, results: list[ModelResult]) -> AggregatedResult:
        if not results:
            return AggregatedResult(
                success=False,
                content="没有可用的结果",
                summary="执行失败：无结果",
            )

        role_results = {r.role: r for r in results}
        
        successful_results = [r for r in results if r.success]
        
        if not successful_results:
            errors = [f"{get_role_definition(r.role).name}: {r.error}" for r in results if r.error]
            return AggregatedResult(
                success=False,
                content="\n".join(errors) if errors else "所有模型执行失败",
                role_results=role_results,
                summary="执行失败",
            )

        all_tool_calls = []
        for r in successful_results:
            all_tool_calls.extend(r.tool_calls)

        content_parts = []
        
        for role in self.role_order:
            if role in role_results and role_results[role].success:
                result = role_results[role]
                role_def = get_role_definition(role)
                
                if result.content and result.content.strip():
                    content_parts.append(f"\n### {role_def.name} ({role_def.description})\n")
                    content_parts.append(result.content)
        
        if not content_parts:
            content_parts = [r.content for r in successful_results if r.content]

        final_content = "\n".join(content_parts)
        summary = self._generate_summary(successful_results)

        return AggregatedResult(
            success=True,
            content=final_content,
            role_results=role_results,
            tool_calls=all_tool_calls,
            summary=summary,
        )

    def _generate_summary(self, results: list[ModelResult]) -> str:
        roles = [get_role_definition(r.role).name for r in results]
        return f"协作完成 - 参与模型: {', '.join(roles)}"

    def format_for_display(self, result: AggregatedResult) -> str:
        lines = []
        
        if result.summary:
            lines.append(f"[摘要] {result.summary}")
        
        if result.role_results:
            lines.append("\n[参与模型]")
            for role, model_result in result.role_results.items():
                role_def = get_role_definition(role)
                status = "✓" if model_result.success else "✗"
                lines.append(f"  {status} {role_def.name}: {role_def.description}")
        
        lines.append("\n[输出内容]")
        lines.append(result.content)
        
        return "\n".join(lines)
