"""
Multi-model orchestration system.
Implements role-based task distribution and parallel execution.
"""

from .roles import ModelRole, RoleDefinition, get_role_definition, get_role_definitions
from .dispatcher import TaskDispatcher, TaskType, SubTask
from .orchestrator import MultiModelOrchestrator
from .aggregator import ResultAggregator, ModelResult, AggregatedResult
from .communication import (
    MessageType,
    Priority,
    ModelMessage,
    HelpRequest,
    Discovery,
    TaskDelegation,
    ValidationResult,
    Handoff,
)
from .state import CollaborationState, SharedContext, TaskProgress
from .coordinator import DynamicCoordinator, WorkflowPhase, TaskComplexity, ExecutionPlan, TaskStep
from .parallel import ParallelCollaborator, ParallelTask, ModuleSpec, ArchitecturePlan

__all__ = [
    "ModelRole",
    "RoleDefinition",
    "get_role_definition",
    "get_role_definitions",
    "TaskDispatcher",
    "TaskType",
    "SubTask",
    "MultiModelOrchestrator",
    "ResultAggregator",
    "ModelResult",
    "AggregatedResult",
    "MessageType",
    "Priority",
    "ModelMessage",
    "HelpRequest",
    "Discovery",
    "TaskDelegation",
    "ValidationResult",
    "Handoff",
    "CollaborationState",
    "SharedContext",
    "TaskProgress",
    "DynamicCoordinator",
    "WorkflowPhase",
    "TaskComplexity",
    "ExecutionPlan",
    "TaskStep",
    "ParallelCollaborator",
    "ParallelTask",
    "ModuleSpec",
    "ArchitecturePlan",
]
