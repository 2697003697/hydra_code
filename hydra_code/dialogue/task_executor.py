"""
任务执行器 - 不同执行模式的统一执行层。
"""

import asyncio
import re
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from pathlib import Path

from ..config import Config
from ..clients import Role
from ..chat import ChatSession
from ..orchestration import DynamicCoordinator, LeaderCollaborator


class ExecutionResult:
    """Result of task execution."""
    
    def __init__(
        self, 
        content: str, 
        success: bool = True,
        mode: str = "unknown",
        metadata: Optional[dict] = None
    ):
        self.content = content
        self.success = success
        self.mode = mode
        self.metadata = metadata or {}


class BaseMode(ABC):
    """Base class for execution modes."""
    
    name: str = "base"
    description: str = ""
    
    def __init__(self, config: Config, working_dir: str):
        self.config = config
        self.working_dir = working_dir
    
    @abstractmethod
    async def run(self, message: str, context: Optional[dict] = None) -> AsyncIterator[str]:
        """Execute the task and yield streaming response."""
        pass
    
    @abstractmethod
    async def run_complete(self, message: str, context: Optional[dict] = None) -> ExecutionResult:
        """Execute the task and return complete result."""
        pass


class TaskExecutor:
    """Unified executor that delegates to specific modes."""
    
    def __init__(self, config: Config, working_dir: str):
        self.config = config
        self.working_dir = working_dir
        self._session: Optional[ChatSession] = None
    
    def _get_session(self) -> ChatSession:
        """Get or create ChatSession."""
        if self._session is None:
            self._session = ChatSession(self.config, self.working_dir)
        return self._session
    
    def _is_retryable_error(self, error: str) -> bool:
        """Check if error is retryable (like 1214 - messages too long)."""
        patterns = [
            r"1214",
            r"messages.*非法",
            r"messages.*too long",
            r"context.*exceed",
            r"max.*tokens.*exceeded",
            r"token.*limit",
            r"error.*code.*1214",
            r"BadRequestError",
        ]
        error_lower = error.lower()
        return any(re.search(p, error_lower) for p in patterns)
    
    def _truncate_messages_for_retry(self, session: ChatSession) -> int:
        """Truncate old messages to reduce context length. Returns count of removed messages."""
        if not session.messages:
            return 0
        
        user_assistant_pairs = []
        current_pair = []
        
        for msg in session.messages:
            role = msg.role.value if hasattr(msg.role, "value") else msg.role
            if role in ["user", "assistant"]:
                current_pair.append(msg)
                if role == "assistant":
                    user_assistant_pairs.append(current_pair)
                    current_pair = []
        
        if current_pair:
            user_assistant_pairs.append(current_pair)
        
        keep_pairs = min(len(user_assistant_pairs), 6)
        keep_messages = []
        for pair in user_assistant_pairs[-keep_pairs:]:
            keep_messages.extend(pair)
        
        removed_count = len(session.messages) - len(keep_messages)
        session.messages = keep_messages
        
        return removed_count
    
    async def execute(
        self, 
        mode: str, 
        message: str, 
        context: Optional[dict] = None,
        max_retries: int = 2
    ) -> AsyncIterator[str]:
        """Execute task in specified mode with streaming and auto-retry."""
        
        session = self._get_session()
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                if mode == "leader":
                    session.set_mode("leader")
                elif mode == "pro":
                    session.set_mode("leader")
                elif mode == "fast":
                    session.set_mode("fast")
                elif mode == "auto":
                    session.set_mode("auto")
                elif mode in ["sonnet", "opus"]:
                    session.set_mode(mode)
                else:
                    session.set_mode("auto")
                
                await session.process_message(message)
                
                if session.messages:
                    download_payload = None
                    for msg in reversed(session.messages):
                        role_value = msg.role.value if hasattr(msg.role, "value") else msg.role
                        if role_value == "tool" and msg.content and msg.content.startswith("DOWNLOAD::"):
                            download_payload = msg.content
                            break

                    assistant_content = None
                    for msg in reversed(session.messages):
                        role_value = msg.role.value if hasattr(msg.role, "value") else msg.role
                        if role_value == "assistant":
                            assistant_content = msg.content or ""
                            break

                    if download_payload:
                        yield download_payload

                    if assistant_content:
                        yield assistant_content
                
                return
                
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                
                if self._is_retryable_error(error_str) and attempt < max_retries:
                    removed = self._truncate_messages_for_retry(session)
                    if removed > 0:
                        yield f"\n\n[Auto-retry: 消息过长，移除 {removed} 条历史消息后重试...]\n"
                        continue
                    else:
                        yield f"\n\n[Error: {error_str}]\n"
                        return
                else:
                    yield f"\n\n[Error: {str(e)}]"
                    return
    
    async def execute_complete(
        self, 
        mode: str, 
        message: str, 
        context: Optional[dict] = None
    ) -> ExecutionResult:
        """Execute task in specified mode and return complete result."""
        
        full_content = ""
        
        try:
            async for chunk in self.execute(mode, message, context):
                full_content += chunk
            
            return ExecutionResult(
                content=full_content,
                success=True,
                mode=mode
            )
        except Exception as e:
            return ExecutionResult(
                content=f"Error: {str(e)}",
                success=False,
                mode=mode
            )
    
    def clear_session(self):
        """Clear the session to start fresh."""
        if self._session:
            self._session.clear_history()
