from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class TodoItem:
    content: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: TaskStatus = TaskStatus.PENDING
    
@dataclass
class TodoList:
    items: list[TodoItem] = field(default_factory=list)
    title: str = "Todo List"
    
    def add_task(self, content: str, status: TaskStatus = TaskStatus.PENDING, id: Optional[str] = None) -> str:
        if id is None:
            id = str(uuid.uuid4())[:8]
        item = TodoItem(content=content, status=status, id=id)
        self.items.append(item)
        return item.id
        
    def update_task(self, id: str, status: TaskStatus) -> bool:
        for item in self.items:
            if item.id == id:
                item.status = status
                return True
        return False

    def clear(self):
        self.items.clear()
        
    def get_task(self, id: str) -> Optional[TodoItem]:
        for item in self.items:
            if item.id == id:
                return item
        return None
