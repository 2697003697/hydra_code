"""
Context Summary - 总结对话历史记录以提供上下文。
"""

import json
import time
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class ConversationSummary:
    """最近对话历史记录的总结。"""
    topics: list[str] = field(default_factory=list)
    key_points: list[str] = field(default_factory=list)
    unresolved_issues: list[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)


class ContextSummary:
    """维护对话上下文的总结。"""
    
    def __init__(self, storage_path: Optional[str] = None, max_history: int = 100):
        self.storage_path = storage_path
        self.max_history = max_history
        self.messages: list[dict] = []
        self.summary = ConversationSummary()
        self.topic_counts: dict[str, int] = defaultdict(int)
        
        if storage_path:
            self.load()
    
    def add_message(self, role: str, content: str, intent: Optional[str] = None):
        """添加一条消息到历史记录。"""
        self.messages.append({
            "role": role,
            "content": content[:500],
            "intent": intent,
            "timestamp": time.time(),
        })
        
        if intent:
            self.topic_counts[intent] += 1
        
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
    
    def update_summary(self):
        """更新对话总结。"""
        if not self.messages:
            return
        
        recent = self.messages[-20:]
        
        intents = [m.get("intent") for m in recent if m.get("intent")]
        if intents:
            self.summary.topics = list(set(intents))[:5]
        
        user_messages = [m["content"] for m in recent if m["role"] == "user"]
        if user_messages:
            self.summary.key_points = user_messages[-3:]
        
        self.summary.last_updated = time.time()
    
    def get_context_for_prompt(self, max_messages: int = 10) -> str:
        """Get context string for system prompt."""
        if not self.messages:
            return ""
        
        recent = self.messages[-max_messages:]
        
        lines = []
        for msg in recent:
            role = msg["role"]
            content = msg["content"][:200]
            lines.append(f"{role}: {content}")
        
        return "\n".join(lines)
    
    def get_recent_intents(self) -> list[str]:
        """Get recent intent history."""
        intents = [m.get("intent") for m in self.messages[-20:] if m.get("intent")]
        return intents
    
    def get_dominant_topic(self) -> Optional[str]:
        """获取最近最常见的主题。"""
        if not self.topic_counts:
            return None
        return max(self.topic_counts, key=self.topic_counts.get)
    
    def should_summarize(self) -> bool:
        """检查是否应该生成新的总结。"""
        return len(self.messages) % 50 == 0
    
    def save(self):
        """保存到磁盘。"""
        if not self.storage_path:
            return
        
        data = {
            "messages": self.messages[-100:],
            "summary": {
                "topics": self.summary.topics,
                "key_points": self.summary.key_points,
                "unresolved_issues": self.summary.unresolved_issues,
                "last_updated": self.summary.last_updated,
            },
            "topic_counts": dict(self.topic_counts),
        }
        
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load(self):
        """从磁盘加载。"""
        if not self.storage_path or not Path(self.storage_path).exists():
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.messages = data.get("messages", [])
            
            summary_data = data.get("summary", {})
            self.summary = ConversationSummary(
                topics=summary_data.get("topics", []),
                key_points=summary_data.get("key_points", []),
                unresolved_issues=summary_data.get("unresolved_issues", []),
                last_updated=summary_data.get("last_updated", time.time()),
            )
            
            self.topic_counts = defaultdict(int, data.get("topic_counts", {}))
        except Exception:
            pass
    
    def clear(self):
        """清除所有历史记录。"""
        self.messages.clear()
        self.topic_counts.clear()
        self.summary = ConversationSummary()
