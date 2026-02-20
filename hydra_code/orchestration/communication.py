"""
Inter-model communication protocol.
Enables models to communicate, request help, and share discoveries.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import time


class MessageType(Enum):
    REQUEST_HELP = "request_help"
    SHARE_DISCOVERY = "share_discovery"
    DELEGATE_TASK = "delegate_task"
    REPORT_PROGRESS = "report_progress"
    ASK_CLARIFICATION = "ask_clarification"
    VALIDATE_RESULT = "validate_result"
    FEEDBACK = "feedback"
    HANDOFF = "handoff"


class Priority(Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 8
    URGENT = 10


@dataclass
class ModelMessage:
    from_role: str
    to_role: Optional[str]
    message_type: MessageType
    content: str
    context: dict[str, Any] = field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    requires_response: bool = False
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: f"msg_{time.time_ns()}")

    def to_dict(self) -> dict:
        return {
            "from": self.from_role,
            "to": self.to_role,
            "type": self.message_type.value,
            "content": self.content,
            "context": self.context,
            "priority": self.priority.value,
            "requires_response": self.requires_response,
            "timestamp": self.timestamp,
            "id": self.id,
        }


@dataclass
class HelpRequest:
    requester: str
    task_description: str
    reason: str
    current_progress: str
    attempted_solutions: list[str] = field(default_factory=list)
    suggested_helper: Optional[str] = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> ModelMessage:
        return ModelMessage(
            from_role=self.requester,
            to_role=self.suggested_helper,
            message_type=MessageType.REQUEST_HELP,
            content=self.task_description,
            context={
                "reason": self.reason,
                "progress": self.current_progress,
                "attempted": self.attempted_solutions,
            },
            requires_response=True,
            priority=Priority.HIGH,
        )


@dataclass
class Discovery:
    discoverer: str
    discovery_type: str
    content: str
    relevance: list[str] = field(default_factory=list)
    confidence: float = 0.8
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> ModelMessage:
        return ModelMessage(
            from_role=self.discoverer,
            to_role=None,
            message_type=MessageType.SHARE_DISCOVERY,
            content=self.content,
            context={
                "type": self.discovery_type,
                "relevance": self.relevance,
                "confidence": self.confidence,
                "metadata": self.metadata,
            },
            priority=Priority.NORMAL,
        )


@dataclass
class TaskDelegation:
    delegator: str
    delegate: str
    task: str
    reason: str
    context_to_share: dict[str, Any] = field(default_factory=dict)
    expected_output: Optional[str] = None

    def to_message(self) -> ModelMessage:
        return ModelMessage(
            from_role=self.delegator,
            to_role=self.delegate,
            message_type=MessageType.DELEGATE_TASK,
            content=self.task,
            context={
                "reason": self.reason,
                "shared_context": self.context_to_share,
                "expected": self.expected_output,
            },
            requires_response=True,
            priority=Priority.HIGH,
        )


@dataclass
class ValidationResult:
    validator: str
    original_author: str
    is_valid: bool
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    improved_version: Optional[str] = None

    def to_message(self) -> ModelMessage:
        return ModelMessage(
            from_role=self.validator,
            to_role=self.original_author,
            message_type=MessageType.VALIDATE_RESULT,
            content=self.improved_version or "",
            context={
                "is_valid": self.is_valid,
                "issues": self.issues,
                "suggestions": self.suggestions,
            },
            requires_response=not self.is_valid,
            priority=Priority.HIGH if not self.is_valid else Priority.NORMAL,
        )


@dataclass
class Handoff:
    from_role: str
    to_role: str
    reason: str
    current_state: dict[str, Any]
    remaining_work: str
    recommendations: list[str] = field(default_factory=list)

    def to_message(self) -> ModelMessage:
        return ModelMessage(
            from_role=self.from_role,
            to_role=self.to_role,
            message_type=MessageType.HANDOFF,
            content=self.remaining_work,
            context={
                "reason": self.reason,
                "state": self.current_state,
                "recommendations": self.recommendations,
            },
            requires_response=True,
            priority=Priority.HIGH,
        )
