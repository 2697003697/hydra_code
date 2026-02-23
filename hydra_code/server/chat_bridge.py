"""
WebSocket 客户端与 DialogueManager 之间的桥梁。
"""

import asyncio
import json
import uuid
from typing import Optional
from urllib.parse import quote
from datetime import datetime

from rich.console import Console

from ..config import Config
from ..dialogue import DialogueManager
from .connection_manager import ConnectionManager, Message

console = Console()


class ChatBridge:
    """Bridges WebSocket connections to DialogueManager."""

    def __init__(self, config: Config, working_dir: str):
        self.config = config
        self.working_dir = working_dir
        self.manager = ConnectionManager()
        self.dialogue_manager: Optional[DialogueManager] = None
        self._processing = False

    async def initialize(self):
        """Initialize dialogue manager."""
        self.dialogue_manager = DialogueManager(self.config, self.working_dir)
        console.print("[green]Dialogue manager initialized for remote access[/green]")

    async def _handle_download_command(self, client_id: str, content: str) -> bool:
        """Handle download command from client."""
        if content.startswith("/download"):
            try:
                parts = content.split(" ", 2)
                if len(parts) >= 2:
                    url = parts[1]
                    path = parts[2] if len(parts) > 2 else None
                    await self.manager.broadcast(Message(
                        id=str(uuid.uuid4()),
                        type="system",
                        content=f"Preparing download: {url}",
                        timestamp=datetime.now().isoformat()
                    ))
                    # Trigger download via dialogue manager if needed, or handle directly
                    # For now, we'll just acknowledge the command
                    return True
            except Exception as e:
                console.print(f"[red]Error parsing download command: {e}[/red]")
        return False

    async def handle_message(self, client_id: str, content: str):
        """Handle incoming message from WebSocket client."""
        if await self._handle_download_command(client_id, content):
            return

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
            user_msg = Message(
                id=str(uuid.uuid4()),
                type="user",
                content=content,
                timestamp=datetime.now().isoformat(),
                metadata={"client_id": client_id}
            )
            await self.manager.broadcast(user_msg)

            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="status",
                content="loading",
                timestamp=datetime.now().isoformat()
            ))

            await self._process_through_dialogue(content)

        except Exception as e:
            console.print(f"[red]Error in handle_message: {e}[/red]")
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="system",
                content=f"Error: {str(e)}",
                timestamp=datetime.now().isoformat()
            ))
        finally:
            self._processing = False
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="status",
                content="idle",
                timestamp=datetime.now().isoformat()
            ))

    async def _process_through_dialogue(self, content: str):
        """Process message through DialogueManager."""
        if not self.dialogue_manager:
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="system",
                content="Dialogue manager not initialized",
                timestamp=datetime.now().isoformat()
            ))
            return

        try:
            async for chunk in self.dialogue_manager.handle_message(content):
                if chunk:
                    if chunk.startswith("DOWNLOAD::"):
                        payload = chunk[len("DOWNLOAD::"):]
                        try:
                            data = json.loads(payload)
                            url = data.get("url")
                            path = data.get("path")
                        except Exception:
                            url = None
                            path = None
                        if url:
                            # Only broadcast file download message if it's a new message
                            # We don't want to re-trigger downloads when replaying history
                            # But here we are processing a new chunk from dialogue manager, so it is new.
                            # However, the frontend might be reconnecting and receiving this from history.
                            # We need to make sure the frontend handles 'file' type messages correctly (e.g. not auto-downloading on history replay)
                            # Or we change the type to 'file_link' which just shows a link.
                            
                            # Let's use a specific type 'file_download_event' for the immediate trigger,
                            # and 'file' for the persistent record.
                            
                            # Actually, better fix is in ConnectionManager to not replay 'file' messages as auto-downloads.
                            # But here, let's just make sure we send a clear message.
                            
                            await self.manager.broadcast(Message(
                                id=str(uuid.uuid4()),
                                type="file", 
                                content=f"下载文件: {path or ''}",
                                timestamp=datetime.now().isoformat(),
                                metadata={"url": url, "path": path, "is_download": True}
                            ))
                        else:
                            await self.manager.broadcast(Message(
                                id=str(uuid.uuid4()),
                                type="system",
                                content="下载参数解析失败",
                                timestamp=datetime.now().isoformat()
                            ))
                        continue
                    await self.manager.broadcast(Message(
                        id=str(uuid.uuid4()),
                        type="assistant",
                        content=chunk,
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
            if self.dialogue_manager:
                self.dialogue_manager.clear_history()
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="system",
                content="History cleared",
                timestamp=datetime.now().isoformat()
            ))
        elif command == "status":
            mode = self.dialogue_manager.get_current_mode() if self.dialogue_manager else "unknown"
            work_mode = self.dialogue_manager.get_work_mode() if self.dialogue_manager else "unknown"
            intent_info = ""
            if self.dialogue_manager and self.dialogue_manager.intent:
                intent_info = f", Intent: {self.dialogue_manager.intent.type.value}"
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="system",
                content=f"Mode: {mode} (work: {work_mode}){intent_info}, Connections: {self.manager.get_connection_count()}",
                timestamp=datetime.now().isoformat()
            ))
        elif command == "mode":
            mode = args.get("mode", "auto")
            if self.dialogue_manager:
                self.dialogue_manager.set_mode(mode)
            await self.manager.broadcast(Message(
                id=str(uuid.uuid4()),
                type="system",
                content=f"Work mode set to: {mode}",
                timestamp=datetime.now().isoformat()
            ))
        elif command == "explain":
            message = args.get("message", "")
            if self.dialogue_manager and message:
                explanation = self.dialogue_manager.explain_routing(message)
                await self.manager.broadcast(Message(
                    id=str(uuid.uuid4()),
                    type="system",
                    content=explanation,
                    timestamp=datetime.now().isoformat()
                ))
