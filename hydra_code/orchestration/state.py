"""
Shared collaboration state management.
Enables models to share context, discoveries, and track progress.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from collections import defaultdict
import time

from .communication import (
    ModelMessage,
    MessageType,
    Discovery,
    HelpRequest,
    TaskDelegation,
    ValidationResult,
    Handoff,
)
from .roles import ModelRole


@dataclass
class TaskProgress:
    task_id: str
    description: str
    assigned_to: list[str]
    status: str = "pending"
    progress: float = 0.0
    sub_results: dict[str, str] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class SharedContext:
    user_request: str
    working_directory: str
    files_read: dict[str, str] = field(default_factory=dict)
    files_modified: dict[str, str] = field(default_factory=dict)
    commands_run: list[dict[str, Any]] = field(default_factory=list)
    discoveries: list[Discovery] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    
    def add_file_context(self, path: str, content: str, by_role: str):
        self.files_read[path] = content
        self.discoveries.append(Discovery(
            discoverer=by_role,
            discovery_type="file_content",
            content=f"Read file: {path}",
            relevance=["file_operations"],
        ))
    
    def add_discovery(self, discovery: Discovery):
        self.discoveries.append(discovery)
    
    def add_decision(self, decision: str, by_role: str, reasoning: str = ""):
        self.decisions.append({
            "decision": decision,
            "by": by_role,
            "reasoning": reasoning,
            "timestamp": time.time(),
        })
    
    def get_relevant_context(self, for_role: str, task: str) -> str:
        parts = []
        
        parts.append(f"原始请求: {self.user_request}")
        
        if self.discoveries:
            parts.append("\n已发现的信息:")
            for d in self.discoveries[-5:]:
                parts.append(f"  [{d.discoverer}] {d.content[:200]}")
        
        if self.decisions:
            parts.append("\n已做出的决策:")
            for dec in self.decisions[-3:]:
                parts.append(f"  [{dec['by']}] {dec['decision']}")
        
        if self.files_read:
            parts.append(f"\n已读取的文件: {', '.join(self.files_read.keys())}")
        
        return "\n".join(parts)


class CollaborationState:
    def __init__(self, user_request: str, working_dir: str):
        self.shared_context = SharedContext(
            user_request=user_request,
            working_directory=working_dir,
        )
        self.message_queue: list[ModelMessage] = []
        self.pending_requests: dict[str, ModelMessage] = {}
        self.task_progress: dict[str, TaskProgress] = {}
        self.role_outputs: dict[str, list[str]] = defaultdict(list)
        self.iteration_count: int = 0
        self.max_iterations: int = 10
        self.is_complete: bool = False
        self.final_result: Optional[str] = None
    
    def broadcast(self, message: ModelMessage):
        self.message_queue.append(message)
        if message.requires_response and message.to_role:
            self.pending_requests[message.id] = message
    
    def get_messages_for(self, role: str) -> list[ModelMessage]:
        messages = []
        remaining = []
        
        for msg in self.message_queue:
            if msg.to_role is None or msg.to_role == role:
                messages.append(msg)
                if not msg.requires_response or msg.to_role != role:
                    remaining.append(msg)
            else:
                remaining.append(msg)
        
        self.message_queue = remaining
        return messages
    
    def respond_to(self, original_id: str, response: ModelMessage):
        if original_id in self.pending_requests:
            del self.pending_requests[original_id]
        self.message_queue.append(response)
    
    def request_help(self, request: HelpRequest) -> str:
        msg = request.to_message()
        self.broadcast(msg)
        return msg.id
    
    def share_discovery(self, discovery: Discovery):
        msg = discovery.to_message()
        self.message_queue.append(msg)
        self.shared_context.add_discovery(discovery)
    
    def delegate_task(self, delegation: TaskDelegation) -> str:
        msg = delegation.to_message()
        self.broadcast(msg)
        return msg.id
    
    def validate_result(self, validation: ValidationResult):
        msg = validation.to_message()
        self.broadcast(msg)
    
    def handoff(self, handoff: Handoff):
        msg = handoff.to_message()
        self.broadcast(msg)
    
    def record_output(self, role: str, output: str):
        self.role_outputs[role].append(output)
    
    def get_role_history(self, role: str) -> list[str]:
        return self.role_outputs.get(role, [])
    
    def create_task(self, task_id: str, description: str, assigned_to: list[str]):
        self.task_progress[task_id] = TaskProgress(
            task_id=task_id,
            description=description,
            assigned_to=assigned_to,
        )
    
    def update_task(self, task_id: str, progress: float, status: str = None):
        if task_id in self.task_progress:
            task = self.task_progress[task_id]
            task.progress = progress
            task.updated_at = time.time()
            if status:
                task.status = status
    
    def add_task_issue(self, task_id: str, issue: str):
        if task_id in self.task_progress:
            self.task_progress[task_id].issues.append(issue)
    
    def get_active_tasks(self) -> list[TaskProgress]:
        return [
            t for t in self.task_progress.values()
            if t.status not in ("completed", "failed")
        ]
    
    def increment_iteration(self) -> bool:
        self.iteration_count += 1
        return self.iteration_count < self.max_iterations
    
    def mark_complete(self, result: str):
        self.is_complete = True
        self.final_result = result
    
    def get_summary(self) -> str:
        lines = [
            f"迭代次数: {self.iteration_count}/{self.max_iterations}",
            f"状态: {'完成' if self.is_complete else '进行中'}",
            f"消息队列: {len(self.message_queue)} 条待处理",
            f"待响应请求: {len(self.pending_requests)} 个",
        ]
        
        if self.shared_context.discoveries:
            lines.append(f"发现: {len(self.shared_context.discoveries)} 条")
        
        if self.shared_context.decisions:
            lines.append(f"决策: {len(self.shared_context.decisions)} 个")
        
        return "\n".join(lines)
