"""
Dialogue Manager - Central hub for handling user conversations.
"""

import asyncio
from typing import AsyncIterator, Optional, List, Any
from dataclasses import dataclass, field

from ..config import Config
from .intent_parser import IntentParser, Intent, IntentType
from .task_router import TaskRouter, ComplexityLevel
from .task_executor import TaskExecutor, ExecutionResult
from .memory import LongTermMemory


@dataclass
class Message:
    """Chat message."""
    role: str
    content: str
    timestamp: float = field(default_factory=lambda: asyncio.get_event_loop().time())


@dataclass 
class DialogueContext:
    """Context for current dialogue."""
    messages: List[Message] = field(default_factory=list)
    current_intent: Optional[Intent] = None
    current_mode: Optional[str] = None
    current_work_mode: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class DialogueManager:
    """Main dialogue handler that coordinates intent parsing, routing, and execution."""
    
    def __init__(self, config: Config, working_dir: str, user_id: str = "default"):
        self.config = config
        self.working_dir = working_dir
        self.user_id = user_id
        
        self.intent_parser = IntentParser()
        self.task_router = TaskRouter(default_mode=config.default_work_mode or "auto")
        self.executor = TaskExecutor(config, working_dir)
        
        self.memory = LongTermMemory(working_dir, user_id)
        
        self.context = DialogueContext()
        self._streaming = True
        self._forced_work_mode: Optional[str] = None
        
        self.memory.record_session_start()
    
    async def handle_message(self, message: str) -> AsyncIterator[str]:
        """Handle user message and yield streaming response."""
        
        user_msg = Message(role="user", content=message)
        self.context.messages.append(user_msg)
        
        intent = self.intent_parser.parse(message)
        self.context.current_intent = intent
        
        intent_hint = self.memory.get_intent_hint(message)
        if intent_hint and intent.type == IntentType.GENERAL:
            intent = self.intent_parser.parse(message)
        
        complexity = self.task_router.assess_complexity(message)
        
        preferred_mode = self.memory.get_favorite_mode()
        if preferred_mode != "auto":
            self.task_router.default_mode = preferred_mode
        
        if self._forced_work_mode and self._forced_work_mode != "auto":
            work_mode = self._forced_work_mode
        else:
            work_mode = self.task_router.route(intent, complexity)
        self.context.current_mode = "chat"
        self.context.current_work_mode = work_mode
        self.context.metadata["work_mode"] = work_mode
        
        self.memory.record_interaction(message, intent.type.value, work_mode)
        
        if self._streaming:
            response_chunks: list[str] = []
            async for chunk in self.executor.execute(work_mode, message, self._get_context_data()):
                if chunk:
                    response_chunks.append(chunk)
                    yield chunk
            if response_chunks:
                full_response = "".join(response_chunks)
                self.context.messages.append(Message(
                    role="assistant",
                    content=full_response
                ))
                self.memory.record_response(full_response, intent.type.value)
        else:
            result = await self.executor.execute_complete(work_mode, message, self._get_context_data())
            yield result.content
    
    async def handle_message_complete(self, message: str) -> ExecutionResult:
        """Handle message and return complete result (non-streaming)."""
        
        user_msg = Message(role="user", content=message)
        self.context.messages.append(user_msg)
        
        intent = self.intent_parser.parse(message)
        self.context.current_intent = intent
        
        complexity = self.task_router.assess_complexity(message)
        if self._forced_work_mode and self._forced_work_mode != "auto":
            work_mode = self._forced_work_mode
        else:
            work_mode = self.task_router.route(intent, complexity)
        self.context.current_mode = "chat"
        self.context.current_work_mode = work_mode
        self.context.metadata["work_mode"] = work_mode
        
        self.memory.record_interaction(message, intent.type.value, work_mode)
        
        result = await self.executor.execute_complete(work_mode, message, self._get_context_data())
        
        if result.success:
            self.context.messages.append(Message(
                role="assistant", 
                content=result.content
            ))
            self.memory.record_response(result.content, intent.type.value)
        
        return result
    
    def _get_context_data(self) -> dict:
        """Get context data for executor."""
        return {
            "intent": self.context.current_intent.type.value if self.context.current_intent else None,
            "mode": self.context.current_work_mode,
            "message_count": len(self.context.messages),
            "metadata": self.context.metadata,
            "memory_hint": self.memory.get_context_hint(),
        }
    
    def set_mode(self, mode: str):
        """Override the routing and use a specific work mode."""
        self.context.current_mode = "chat"
        self.context.current_work_mode = mode
        self.context.metadata["work_mode"] = mode
        if mode == "auto":
            self._forced_work_mode = None
        else:
            self._forced_work_mode = mode
    
    def get_current_mode(self) -> str:
        """Get current execution mode."""
        return self.context.current_mode or "chat"

    def get_work_mode(self) -> str:
        """Get current work layer mode."""
        return self.context.current_work_mode or "auto"
    
    def get_recent_messages(self, count: int = 10) -> List[Message]:
        """Get recent messages."""
        return self.context.messages[-count:]
    
    def clear_history(self):
        """Clear message history."""
        self.context.messages.clear()
        self.context.current_intent = None
        self.context.current_mode = None
        self.context.current_work_mode = None
        self._forced_work_mode = None
        self.executor.clear_session()
    
    @property
    def intent(self) -> Optional[Intent]:
        """Get current intent."""
        return self.context.current_intent
    
    @property
    def mode(self) -> str:
        """Get current mode."""
        return self.get_current_mode()
    
    def explain_routing(self, message: str) -> str:
        """Explain how a message would be routed (for debugging)."""
        intent = self.intent_parser.parse(message)
        complexity = self.task_router.assess_complexity(message)
        work_mode = self.task_router.route(intent, complexity)
        
        user_context = self.memory.user_profile.get_context_summary()
        
        return f"""Intent Analysis:
- Type: {intent.type.value} (confidence: {intent.confidence:.2f})
- Complexity: {complexity}
- Routed to: {work_mode}
- Entities: {intent.entities}

[Learned User Context]:
{user_context if user_context else "(Not enough data yet)"}"""


class SimpleDialogueManager(DialogueManager):
    """Simplified dialogue manager without complexity assessment."""
    
    def __init__(self, config: Config, working_dir: str, user_id: str = "default"):
        from .task_router import SimpleTaskRouter
        super().__init__(config, working_dir, user_id)
        self.task_router = SimpleTaskRouter(default_mode=config.default_work_mode or "auto")
