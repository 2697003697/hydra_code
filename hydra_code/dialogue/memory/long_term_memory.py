"""
Long-term Memory - Integrates all memory systems.
"""

import os
from pathlib import Path
from typing import Optional

from .user_profile import UserProfile
from .habit_memory import HabitMemory
from .context_summary import ContextSummary


class LongTermMemory:
    """Unified long-term memory system."""
    
    def __init__(self, working_dir: str, user_id: str = "default"):
        self.working_dir = working_dir
        self.user_id = user_id
        
        self._memory_dir = Path(working_dir) / ".hydra" / "memory" / user_id
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        
        self._profile_path = str(self._memory_dir / "profile.json")
        self._habits_path = str(self._memory_dir / "habits.json")
        self._context_path = str(self._memory_dir / "context.json")
        
        self.user_profile = UserProfile(self._profile_path)
        self.habit_memory = HabitMemory(self._habits_path)
        self.context_summary = ContextSummary(self._context_path)
    
    def record_interaction(self, message: str, intent: str, mode: str):
        """Record a complete interaction for learning."""
        self.user_profile.record_message(message, intent, mode)
        self.habit_memory.record_message(message, intent)
        self.context_summary.add_message("user", message, intent)
        
        self.save()
    
    def record_response(self, content: str, intent: Optional[str] = None):
        """Record assistant response."""
        self.context_summary.add_message("assistant", content, intent)
        
        if self.context_summary.should_summarize():
            self.context_summary.update_summary()
        
        self.save()
    
    def record_session_start(self):
        """Record the start of a new session."""
        self.user_profile.record_session_start()
        self.save()
    
    def enhance_prompt(self) -> str:
        """Get enhancements for system prompt."""
        return self.user_profile.get_system_prompt_addition()
    
    def get_context_hint(self) -> str:
        """Get contextual hints."""
        return self.habit_memory.get_context_hint()
    
    def get_intent_hint(self, message: str) -> Optional[str]:
        """Get intent hint based on habits."""
        return self.habit_memory.get_preferred_intent(message)
    
    def get_favorite_mode(self) -> str:
        """Get user's favorite mode."""
        return self.user_profile.get_favorite_mode()
    
    def clear(self):
        """Clear all memory."""
        self.user_profile = UserProfile(self._profile_path)
        self.habit_memory = HabitMemory(self._habits_path)
        self.context_summary = ContextSummary(self._context_path)
        self.save()
    
    def save(self):
        """Save all memory components."""
        self.user_profile.save()
        self.habit_memory.save()
        self.context_summary.save()
