"""
User Profile - Stores and learns user preferences over time.
"""

import json
import time
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class Preference:
    """A single preference entry."""
    key: str
    value: Any
    confidence: float = 1.0
    updated_at: float = field(default_factory=time.time)
    source: str = "inferred"


class UserProfile:
    """Learns and stores user preferences over time."""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path
        self.preferences: dict[str, Preference] = {}
        self.usage_stats: dict[str, Any] = {
            "total_messages": 0,
            "total_sessions": 0,
            "favorite_modes": {},
            "common_intents": {},
            "first_seen": time.time(),
            "last_seen": time.time(),
        }
        
        if storage_path:
            self.load()
    
    def record_message(self, message: str, intent: str, mode: str):
        """Record a message interaction for learning."""
        self.usage_stats["total_messages"] += 1
        self.usage_stats["last_seen"] = time.time()
        
        self.usage_stats["favorite_modes"][mode] = \
            self.usage_stats["favorite_modes"].get(mode, 0) + 1
        
        self.usage_stats["common_intents"][intent] = \
            self.usage_stats["common_intents"].get(intent, 0) + 1
    
    def record_session_start(self):
        """Record a new session."""
        self.usage_stats["total_sessions"] += 1
        self.usage_stats["last_seen"] = time.time()
    
    def set_preference(self, key: str, value: Any, confidence: float = 0.8, source: str = "explicit"):
        """Set a user preference."""
        existing = self.preferences.get(key)
        if existing:
            if confidence > existing.confidence:
                self.preferences[key] = Preference(
                    key=key,
                    value=value,
                    confidence=confidence,
                    source=source
                )
        else:
            self.preferences[key] = Preference(
                key=key,
                value=value,
                confidence=confidence,
                source=source
            )
    
    def infer_preference(self, key: str, value: Any):
        """Infer a preference from user behavior."""
        self.set_preference(key, value, confidence=0.5, source="inferred")
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a preference value."""
        pref = self.preferences.get(key)
        if pref and pref.confidence > 0.3:
            return pref.value
        return default
    
    def get_favorite_mode(self) -> str:
        """Get user's most used mode."""
        modes = self.usage_stats.get("favorite_modes", {})
        if not modes:
            return "auto"
        return max(modes, key=modes.get)
    
    def get_context_summary(self) -> str:
        """Get a summary of user for context."""
        lines = []
        
        favorite_mode = self.get_favorite_mode()
        lines.append(f"- 常用模式: {favorite_mode}")
        
        total = self.usage_stats.get("total_messages", 0)
        if total > 0:
            lines.append(f"- 总消息数: {total}")
        
        common_intents = self.usage_stats.get("common_intents", {})
        if common_intents:
            top_intent = max(common_intents, key=common_intents.get)
            lines.append(f"- 常见操作: {top_intent}")
        
        return "\n".join(lines)
    
    def get_system_prompt_addition(self) -> str:
        """Get user context for system prompt."""
        if self.usage_stats["total_messages"] < 5:
            return ""
        
        summary = self.get_context_summary()
        return f"\n\n[User Context - learned over time]:\n{summary}"
    
    def save(self):
        """Save profile to disk."""
        if not self.storage_path:
            return
        
        data = {
            "preferences": {k: asdict(v) for k, v in self.preferences.items()},
            "usage_stats": self.usage_stats,
        }
        
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load(self):
        """Load profile from disk."""
        if not self.storage_path or not Path(self.storage_path).exists():
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.preferences = {
                k: Preference(**v) for k, v in data.get("preferences", {}).items()
            }
            self.usage_stats = data.get("usage_stats", self.usage_stats)
        except Exception:
            pass
