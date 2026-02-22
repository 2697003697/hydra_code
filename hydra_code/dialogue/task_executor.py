"""
Task Executor - Unified execution layer for different modes.
"""

import asyncio
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
    
    async def execute(
        self, 
        mode: str, 
        message: str, 
        context: Optional[dict] = None
    ) -> AsyncIterator[str]:
        """Execute task in specified mode with streaming."""
        
        session = self._get_session()
        
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
                
        except Exception as e:
            yield f"\n\n[Error: {str(e)}]"
    
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
