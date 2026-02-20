"""
Simple API call statistics tracking.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class APICallStats:
    total_calls: int = 0
    calls_by_role: Dict[str, int] = field(default_factory=dict)
    total_tokens_estimate: int = 0
    
    def record_call(self, role: str = "unknown", tokens_estimate: int = 0):
        self.total_calls += 1
        self.calls_by_role[role] = self.calls_by_role.get(role, 0) + 1
        self.total_tokens_estimate += tokens_estimate
    
    def reset(self):
        self.total_calls = 0
        self.calls_by_role.clear()
        self.total_tokens_estimate = 0
    
    def get_summary(self) -> str:
        lines = [
            f"API调用统计:",
            f"  总调用次数: {self.total_calls}",
        ]
        if self.calls_by_role:
            lines.append("  按角色:")
            for role, count in self.calls_by_role.items():
                lines.append(f"    {role}: {count}次")
        if self.total_tokens_estimate > 0:
            lines.append(f"  估计tokens: ~{self.total_tokens_estimate}")
        return "\n".join(lines)


_global_stats = APICallStats()


def get_stats() -> APICallStats:
    return _global_stats


def record_call(role: str = "unknown", tokens_estimate: int = 0):
    _global_stats.record_call(role, tokens_estimate)


def reset_stats():
    _global_stats.reset()
