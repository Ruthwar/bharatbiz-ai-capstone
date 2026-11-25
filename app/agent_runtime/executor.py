"""Bounded execution of a plan.

The executor is the only place tools run. It enforces three caps before every call
(steps, estimated tokens, wall clock), refuses to repeat an identical call more than twice
(loop guard), resolves the two derived arguments used by the planner, and records every
attempt as an observation instead of raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agent_runtime.budget import AgentBudget, estimate_tokens
from app.agent_runtime.planner import AgentPlan, PlannedStep
from app.agent_runtime.registry import (
    ToolError,
    ToolRegistry,
    auto_horizon,
    canonical_args,
)
from app.observability import record_span
from app.schemas.contracts import BusinessState

MAX_IDENTICAL_CALLS = 2


@dataclass
class StepObservation:
    step_id: str
    tool: str
    args: dict
    attempt: int
    status: str
    output: dict = field(default_factory=dict)
    code: str | None = None
    error: str | None = None
    latency_ms: float = 0.0
    estimated_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "tool": self.tool,
            "args": self.args,
            "attempt": self.attempt,
            "status": self.status,
            "output": self.output,
            "code": self.code,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "estimated_tokens": self.estimated_tokens,
        }


def _latest(observations: list[StepObservation], tool: str) -> dict | None:
    for observation in reversed(observations):
        if observation.tool == tool and observation.status == "ok":
            return observation.output
    return None


def _resolve_args(step: PlannedStep, observations: list[StepObservation], state: BusinessState) -> dict:
    args = dict(step.args)
    if step.tool != "supplier_options":
        return args
    if args.get("required_units") == "auto":
        inventory = _latest(observations, "inventory_position") or {}
        orders = _latest(observations, "open_orders") or {}
        available = (inventory.get("proposal") or {}).get("immediately_available_units")
        requested = orders.get("total_requested_units")
        if available is None or requested is None:
            args["required_units"] = 0
        else:
            args["required_units"] = max(int(requested) - int(available), 0)
    if args.get("planning_horizon") == "auto":
        args["planning_horizon"] = auto_horizon(state, _latest(observations, "open_orders"))
    return args


def execute_plan(
    plan: AgentPlan,
    registry: ToolRegistry,
    budget: AgentBudget,
    state: BusinessState,
    *,
    attempt: int = 1,
    only_step_ids: set[str] | None = None,
    observations: list[StepObservation] | None = None,
    signature_counts: dict[str, int] | None = None,
) -> list[StepObservation]:
    """Run the selected steps and return one observation per attempt, including refusals."""
    history = observations if observations is not None else []
    signatures = signature_counts if signature_counts is not None else {}
    produced: list[StepObservation] = []
    for step in plan.steps:
        if only_step_ids is not None and step.step_id not in only_step_ids:
            continue
        stop = budget.stop_reason()
        if stop is not None:
            produced.append(
                StepObservation(
                    step_id=step.step_id,
                    tool=step.tool,
                    args=step.args,
                    attempt=attempt,
                    status="skipped",
                    code=stop,
                    error=f"Agent budget reached before this step ({stop}).",
                )
            )
            continue
        try:
            args = _resolve_args(step, [*history, *produced], state)
        except (TypeError, ValueError) as exc:
            produced.append(
                StepObservation(
                    step_id=step.step_id,
                    tool=step.tool,
                    args=step.args,
                    attempt=attempt,
                    status="error",
                    code="malformed_arguments",
                    error=str(exc),
                )
            )
            continue
        signature = f"{step.tool}|{canonical_args(args)}"
        signatures[signature] = signatures.get(signature, 0) + 1
        if signatures[signature] > MAX_IDENTICAL_CALLS:
            produced.append(
                StepObservation(
                    step_id=step.step_id,
                    tool=step.tool,
                    args=args,
                    attempt=attempt,
                    status="error",
                    code="loop_guard",
                    error=f"Identical call refused after {MAX_IDENTICAL_CALLS} attempts.",
                )
            )
            record_span(
                f"tool:{step.tool}",
                "tool",
                status="error",
                error="loop_guard",
                detail={"step_id": step.step_id, "attempt": attempt, "args": args},
            )
            continue
        budget.take_step()
        try:
            result = registry.call(step.tool, args)
        except ToolError as exc:
            cost = estimate_tokens(canonical_args(args) + exc.message)
            budget.charge(canonical_args(args) + exc.message)
            produced.append(
                StepObservation(
                    step_id=step.step_id,
                    tool=step.tool,
                    args=args,
                    attempt=attempt,
                    status="error",
                    code=exc.code,
                    error=exc.message,
                    estimated_tokens=cost,
                )
            )
            record_span(
                f"tool:{step.tool}",
                "tool",
                status="error",
                error=exc.message,
                detail={"step_id": step.step_id, "attempt": attempt, "args": args, "code": exc.code},
            )
            continue
        budget.charge(canonical_args(args) + canonical_args(result.output))
        produced.append(
            StepObservation(
                step_id=step.step_id,
                tool=step.tool,
                args=args,
                attempt=attempt,
                status="ok",
                output=result.output,
                latency_ms=result.latency_ms,
                estimated_tokens=result.estimated_tokens,
            )
        )
        record_span(
            f"tool:{step.tool}",
            "tool",
            latency_ms=result.latency_ms,
            detail={
                "step_id": step.step_id,
                "attempt": attempt,
                "args": args,
                "estimated_tokens": result.estimated_tokens,
            },
        )
    return produced
