"""
Bridge between WebSocket clients and ChatSession.
"""

import asyncio
import uuid
from typing import Optional
from datetime import datetime

from rich.console import Console

from ..chat import ChatSession
from ..config import Config
from .connection_manager import ConnectionManager, Message

console = Console()


class ChatBridge:
    """Bridges WebSocket connections to ChatSession."""

    def __init__(self, config: Config, working_dir: str):
        self.config = config
        self.working_dir = working_dir
        self.manager = ConnectionManager()
        self.session: Optional[ChatSession] = None
        self._processing = False

    async def initialize(self):
        """Initialize chat session."""
        self.session = ChatSession(self.config, self.working_dir)
        console.print("[green]Chat session initialized for remote access[/green]")

    async def handle_message(self, client_id: str, content: str):
        """Handle incoming message from WebSocket client."""
        if self._processing:
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="system",
                content="Previous request still processing...",
                timestamp=datetime.now().isoformat()
            ))
            return

        self._processing = True

        try:
            # Broadcast user message
            user_msg = Message(
                id=str(uuid.uuid4()),
                type="user",
                content=content,
                timestamp=datetime.now().isoformat(),
                metadata={"client_id": client_id}
            )
            await self.manager.broadcast(user_msg)

            # Process through ChatSession
            await self._process_through_session(content)

        except Exception as e:
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="system",
                content=f"Error: {str(e)}",
                timestamp=datetime.now().isoformat()
            ))
        finally:
            self._processing = False

    async def _process_through_session(self, content: str):
        """Process message through existing ChatSession."""
        if not self.session:
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="system",
                content="Session not initialized",
                timestamp=datetime.now().isoformat()
            ))
            return

        # Create a custom output handler that broadcasts to WebSocket
        output_buffer = []
        
        # For now, we'll use a simple approach
        # In a full implementation, we'd need to modify ChatSession to support streaming callbacks
        
        try:
            # This is a simplified version - full implementation would need
            # to hook into the ChatSession's streaming output
            await self.session.process_message(content)
            
            # Get the last assistant message
            if self.session.messages:
                last_msg = self.session.messages[-1]
                if last_msg.role.value == "assistant":
                    await self.manager.broadcast(Message(
                        id=str(uuid.uuid4()),
                        type="assistant",
                        content=last_msg.content or "",
                        timestamp=datetime.now().isoformat()
                    ))
        except Exception as e:
            console.print(f"[red]Error processing message: {e}[/red]")
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="system",
                content=f"Processing error: {str(e)}",
                timestamp=datetime.now().isoformat()
            ))

    async def handle_command(self, client_id: str, command: str, args: dict):
        """Handle special commands from client."""
        if command == "clear":
            if self.session:
                self.session.clear_history()
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="system",
                content="History cleared",
                timestamp=datetime.now().isoformat()
            ))
        elif command == "status":
            await self.manager.broadcast_status(
                "ready",
                {
                    "connections": self.manager.get_connection_count(),
                    "mode": self.session.config.default_role if self.session else "unknown"
                }
            )
        elif command == "mode":
            mode = args.get("mode", "auto")
            if self.session:
                self.session.set_mode(mode)
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="system",
                content=f"Mode set to: {mode}",
                timestamp=datetime.now().isoformat()
            ))
