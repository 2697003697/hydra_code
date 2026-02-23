"""
任务路由 - 将任务路由到适当的执行模式。
"""

from typing import Optional

from .intent_parser import Intent, IntentType


class ComplexityLevel:
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class TaskRouter:
    """Routes intents to appropriate execution modes."""

    DEFAULT_MODE = "auto"

    ROUTE_RULES = {
        IntentType.QUESTION: "fast",
        IntentType.SEARCH: "fast",
        IntentType.EXPLAIN: "fast",
        IntentType.CODE: "auto",
        IntentType.MODIFY: "auto",
        IntentType.DEBUG: "auto",
        IntentType.REFACTOR: "pro",
        IntentType.PROJECT: "auto",
        IntentType.ADMIN: "fast",
        IntentType.GENERAL: "fast",
    }

    COMPLEXITY_KEYWORDS = {
        ComplexityLevel.SIMPLE: [
            "简单", "小", "一下", "个", "帮我", "怎么", "什么是",
        ],
        ComplexityLevel.MODERATE: [
            "函数", "类", "模块", "多个", "一些",
        ],
        ComplexityLevel.COMPLEX: [
            "重构", "系统", "架构", "项目", "完整", "全面",
            "整个", "大规模", "企业级",
        ],
    }

    def __init__(self, default_mode: str = "auto"):
        self.default_mode = default_mode

    def assess_complexity(self, message: str) -> str:
        """Assess task complexity based on message."""
        
        message_lower = message.lower()
        
        complex_score = sum(1 for kw in self.COMPLEXITY_KEYWORDS[ComplexityLevel.COMPLEX] if kw in message_lower)
        simple_score = sum(1 for kw in self.COMPLEXITY_KEYWORDS[ComplexityLevel.SIMPLE] if kw in message_lower)
        
        if complex_score > simple_score:
            return ComplexityLevel.COMPLEX
        elif simple_score > complex_score:
            return ComplexityLevel.SIMPLE
        else:
            return ComplexityLevel.MODERATE

    def route(self, intent: Intent, complexity: Optional[str] = None) -> str:
        """Route intent to appropriate execution mode."""
        
        base_mode = self.ROUTE_RULES.get(intent.type, self.default_mode)
        
        if complexity is None:
            complexity = self.assess_complexity(intent.original_message)
        
        if complexity == ComplexityLevel.COMPLEX and base_mode == "auto":
            return "pro"
        
        if complexity == ComplexityLevel.SIMPLE and base_mode == "auto":
            return "fast"
        
        return base_mode

    def route_by_message(self, message: str) -> str:
        """Convenience method to route directly from message."""
        intent = IntentParser().parse(message)
        complexity = self.assess_complexity(message)
        return self.route(intent, complexity)


class SimpleTaskRouter(TaskRouter):
    """Simpler router without complexity assessment."""
    
    def route(self, intent: Intent, complexity: Optional[str] = None) -> str:
        return self.ROUTE_RULES.get(intent.type, self.default_mode)


from .intent_parser import IntentParser
