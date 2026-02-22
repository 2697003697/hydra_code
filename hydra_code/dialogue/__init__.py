"""
Dialogue layer for Hydra Code.
Provides intent parsing, task routing, and unified message handling.
"""

from .intent_parser import IntentParser, Intent, IntentType
from .task_router import TaskRouter
from .dialogue_manager import DialogueManager
from .task_executor import TaskExecutor
from .memory import LongTermMemory, UserProfile, HabitMemory, ContextSummary

__all__ = [
    "IntentParser",
    "Intent", 
    "IntentType",
    "TaskRouter",
    "DialogueManager",
    "TaskExecutor",
    "LongTermMemory",
    "UserProfile",
    "HabitMemory",
    "ContextSummary",
]
