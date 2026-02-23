"""
Habit Memory - 跟踪用户习惯和行为模式。
"""

import json
import time
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class HabitEntry:
    """一个习惯或模式条目。"""
    pattern: str
    count: int = 1
    last_seen: float = field(default_factory=time.time)
    examples: list[str] = field(default_factory=list)


class HabitMemory:
    """学习和记住用户习惯和模式。"""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path
        self.habits: dict[str, HabitEntry] = {}
        self.phrase_mappings: dict[str, str] = {}
        self.word_preferences: dict[str, str] = {}
        
        if storage_path:
            self.load()
    
    def record_message(self, message: str, intent: str):
        """记录一条消息以学习模式。"""
        message_lower = message.lower()
        
        self._learn_abbreviations(message_lower)
        self._learn_word_preferences(message_lower, intent)
        self._learn_common_phrases(message_lower, intent)
    
    def _learn_abbreviations(self, message: str):
        """学习用户可能使用的常见缩写。"""
        abbreviations = {
            "重写": "refactor",
            "解释": "explain", 
            "查": "search",
            "找": "search",
            "写": "code",
            "改": "modify",
            "修": "debug",
        }
        
        for cn, en in abbreviations.items():
            if cn in message:
                if cn not in self.phrase_mappings:
                    self.phrase_mappings[cn] = en
    
    def _learn_word_preferences(self, message: str, intent: str):
        """学习用户的单词偏好。"""
        preference_patterns = [
            ("请", "polite"),
            ("帮我", "helpful"),
            ("能不能", "questioning"),
        ]
        
        for pattern, pref in preference_patterns:
            if pattern in message:
                self.word_preferences[pref] = \
                    self.word_preferences.get(pref, 0) + 1
    
    def _learn_common_phrases(self, message: str, intent: str):
        """学习每个意图的常见短语。"""
        if intent not in self.habits:
            self.habits[intent] = HabitEntry(pattern=intent)
        
        entry = self.habits[intent]
        entry.count += 1
        entry.last_seen = time.time()
        
        if len(entry.examples) < 10:
            entry.examples.append(message[:100])
    
    def get_preferred_intent(self, message: str) -> Optional[str]:
        """尝试根据习惯将消息映射到首选意图。"""
        message_lower = message.lower()
        
        for phrase, intent in self.phrase_mappings.items():
            if phrase in message_lower:
                return intent
        
        return None
    
    def get_communication_style(self) -> str:
        """获取用户的首选沟通风格。"""
        if not self.word_preferences:
            return "neutral"
        
        style = max(self.word_preferences, key=self.word_preferences.get)
        
        style_map = {
            "polite": "请使用礼貌的语气",
            "helpful": "请使用帮助性的语气",
            "questioning": "请使用解释性的语气",
        }
        
        return style_map.get(style, "neutral")
    
    def get_common_intents(self, limit: int = 3) -> list[str]:
        """获取用户常用的意图。"""
        if not self.habits:
            return []
        
        sorted_habits = sorted(
            self.habits.values(),
            key=lambda x: x.count,
            reverse=True
        )
        
        return [h.pattern for h in sorted_habits[:limit]]
    
    def get_context_hint(self) -> str:
        """获取用户习惯的上下文提示。"""
        hints = []
        
        common_intents = self.get_common_intents(2)
        if common_intents:
            hints.append(f"用户常用的操作: {', '.join(common_intents)}")
        
        style = self.get_communication_style()
        if style != "neutral":
            hints.append(f"沟通风格偏好: {style}")
        
        return " | ".join(hints) if hints else ""
    
    def save(self):
        """保存习惯到磁盘。"""
        if not self.storage_path:
            return
        
        data = {
            "habits": {k: {
                "pattern": v.pattern,
                "count": v.count,
                "last_seen": v.last_seen,
                "examples": v.examples,
            } for k, v in self.habits.items()},
            "phrase_mappings": self.phrase_mappings,
            "word_preferences": self.word_preferences,
        }
        
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load(self):
        """Load habits from disk."""
        if not self.storage_path or not Path(self.storage_path).exists():
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.habits = {
                k: HabitEntry(**v) for k, v in data.get("habits", {}).items()
            }
            self.phrase_mappings = data.get("phrase_mappings", {})
            self.word_preferences = data.get("word_preferences", {})
        except Exception:
            pass
