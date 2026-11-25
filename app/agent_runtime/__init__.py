"""Bounded, read-only agent runtime: planner -> executor -> critic.

The runtime exists to make the review path inspectable, not to act. Every tool reads the
synthetic state or the approved corpus; nothing here purchases, pays, prices, allocates
stock or messages a party. A run records its plan, each tool call, the critic's findings,
retries and budget use so a reviewer can audit the reasoning.
"""

from app.agent_runtime.critic import Critique, Finding, critique
from app.agent_runtime.executor import AgentBudget, StepObservation, execute_plan, estimate_tokens
from app.agent_runtime.planner import (
    AgentPlan,
    PlanValidationError,
    PlannedStep,
    build_plan,
    parse_plan,
    resolve_context,
)
from app.agent_runtime.registry import (
    ToolError,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    build_registry,
    tool_catalog,
)
from app.agent_runtime.runtime import (
    FAILURE_TAXONOMY,
    AgentRequest,
    AgentRun,
    agent_store,
    run_review,
)
from app.agent_runtime.store import AgentSessionStore

__all__ = [
    "FAILURE_TAXONOMY",
    "AgentBudget",
    "AgentPlan",
    "AgentRequest",
    "AgentRun",
    "AgentSessionStore",
    "Critique",
    "Finding",
    "PlanValidationError",
    "PlannedStep",
    "StepObservation",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "agent_store",
    "build_plan",
    "build_registry",
    "critique",
    "estimate_tokens",
    "execute_plan",
    "parse_plan",
    "resolve_context",
    "run_review",
    "tool_catalog",
]
