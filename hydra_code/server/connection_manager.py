"""
WebSocket connection manager for handling multiple clients.
"""

import asyncio
import json
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime

from fastapi import WebSocket


@dataclass
class Message:
    """Message structure for WebSocket communication."""
    id: str
    type: str  # "user", "assistant", "system", "tool", "status"
    content: str
    timestamp: str
    metadata: Optional[dict] = None


class ConnectionManager:
    """Manages WebSocket connections and message broadcasting."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.message_history: List[Message] = []
        self.max_history = 100
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection."""
        await websocket.accept()
        
        async with self._lock:
            self.active_connections.append(websocket)
        
        # Send connection confirmation only (no history to avoid re-sending on reconnect)
        await self.send_personal_message(
            websocket,
            Message(
                id="system-1",
                type="system",
                content="Connected to Hydra Code server",
                timestamp=datetime.now().isoformat(),
                metadata={"status": "connected"}
            )
        )

    async def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def send_personal_message(self, websocket: WebSocket, message: Message):
        """Send message to specific client."""
        try:
            await websocket.send_json(asdict(message))
        except Exception:
            pass

    async def broadcast(self, message: Message):
        """Broadcast message to all connected clients."""
        # Add to history
        async with self._lock:
            self.message_history.append(message)
            if len(self.message_history) > self.max_history:
                self.message_history = self.message_history[-self.max_history:]

        # Broadcast to all connections
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(asdict(message))
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        async with self._lock:
            for conn in disconnected:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)

    async def broadcast_status(self, status: str, metadata: Optional[dict] = None):
        """Broadcast status update."""
        await self.broadcast(Message(
            id=f"status-{datetime.now().timestamp()}",
            type="status",
            content=status,
            timestamp=datetime.now().isoformat(),
            metadata=metadata
        ))

    def get_connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)
