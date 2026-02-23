"""
意图解析器 - 分析用户消息以确定意图。
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class IntentType(Enum):
    QUESTION = "question"
    CODE = "code"
    MODIFY = "modify"
    DEBUG = "debug"
    REFACTOR = "refactor"
    EXPLAIN = "explain"
    SEARCH = "search"
    PROJECT = "project"
    ADMIN = "admin"
    GENERAL = "general"


@dataclass
class Intent:
    type: IntentType
    confidence: float
    entities: dict = field(default_factory=dict)
    context: str = ""
    original_message: str = ""


class IntentParser:
    """Parses user messages to identify intent and extract entities."""

    PATTERNS = {
        IntentType.CODE: [
            r"写(个?|一个)?(函数|类|算法|程序|代码)",
            r"帮我写",
            r"创建(一个)?(函数|类|组件)",
            r"实现(一个)?",
            r"how to (write|create|implement|build)",
        ],
        IntentType.MODIFY: [
            r"修改|改动|改一下",
            r"把.*改成?",
            r"把.*替换成?",
            r"refactor|rewrite|update|change.*to",
            r"改进(一下)?",
            r"优化(一下)?",
        ],
        IntentType.DEBUG: [
            r"为什么(报错|出错|不行)?",
            r".*报错.*",
            r".*出错了.*",
            r"fix.*bug|debug",
            r"(解|解一下)决.*问题",
            r".*不工作.*",
            r".*失败了.*",
        ],
        IntentType.EXPLAIN: [
            r"什么意思",
            r"解释(一下)?",
            r"是什么",
            r"(讲|说)解(一下)?",
            r"explain|what is|what does",
            r"这段代码.*",
        ],
        IntentType.QUESTION: [
            r"^(?!.*(帮我|请|帮我)).*(怎么|如何|什么|为什么|能否|可以|是否)",
            r"是不是",
            r"有没有",
            r"how (do|can|to)",
            r"what (is|are|does)",
            r"why ",
            r"\\?$",
        ],
        IntentType.SEARCH: [
            r"搜索?|查找|找(一下)?",
            r"在哪里",
            r"search|find|locate",
            r"列出.*所有",
        ],
        IntentType.REFACTOR: [
            r"重构",
            r"重写",
            r"整理(一下)?",
            r"优化(代码)?",
        ],
        IntentType.PROJECT: [
            r"初始化(项目)?",
            r"创建项目",
            r"新建项目",
            r"setup|init|create.*project",
        ],
        IntentType.ADMIN: [
            r"/(help|quit|exit|clear|restart)",
            r"帮助|退出|清除|重启",
            r"设置|配置",
        ],
    }

    KEYWORDS = {
        IntentType.CODE: ["写", "创建", "实现", "编写", "write", "create", "implement"],
        IntentType.MODIFY: ["修改", "改", "替换", "更新", "change", "update", "modify"],
        IntentType.DEBUG: ["报错", "错误", "失败", "bug", "问题", "fix", "debug", "error"],
        IntentType.EXPLAIN: ["解释", "意思", "什么", "explain", "what"],
        IntentType.QUESTION: ["怎么", "如何", "什么", "为什么", "how", "what", "why"],
        IntentType.SEARCH: ["搜索", "查找", "找", "search", "find"],
        IntentType.REFACTOR: ["重构", "重写", "优化"],
        IntentType.PROJECT: ["初始化", "创建项目", "新建"],
    }

    def __init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        self._compiled_patterns = {}
        for intent_type, patterns in self.PATTERNS.items():
            self._compiled_patterns[intent_type] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def parse(self, message: str) -> Intent:
        """Parse message and return intent with confidence."""
        
        message = message.strip()
        if not message:
            return Intent(
                type=IntentType.GENERAL,
                confidence=0.0,
                original_message=message
            )

        best_intent = IntentType.GENERAL
        best_score = 0.0
        entities = {}

        for intent_type, patterns in self._compiled_patterns.items():
            score = 0.0
            
            for pattern in patterns:
                if match := pattern.search(message):
                    score += 1.0
                    if intent_type == IntentType.CODE and "函数" in match.group():
                        entities["type"] = "function"
                    elif intent_type == IntentType.CODE and "类" in match.group():
                        entities["type"] = "class"
                    elif intent_type == IntentType.DEBUG:
                        entities["error_info"] = match.group()

            if score > best_score:
                best_score = score
                best_intent = intent_type

        confidence = min(best_score / 2.0, 1.0) if best_score > 0 else 0.5

        return Intent(
            type=best_intent,
            confidence=confidence,
            entities=entities,
            original_message=message
        )

    def parse_simple(self, message: str) -> IntentType:
        """Simple parsing without confidence scoring."""
        return self.parse(message).type
