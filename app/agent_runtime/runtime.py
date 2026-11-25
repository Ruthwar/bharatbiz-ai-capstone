"""The planner -> executor -> critic loop, with one retry round and a recorded audit trail.

A run never writes business state. It reads the synthetic state and the approved corpus,
records every step and finding, and returns a bounded report. Human approval still happens
in the review ledger, not here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.agent_runtime.budget import TOKEN_ESTIMATE_BASIS, AgentBudget
from app.agent_runtime.critic import Critique, critique
from app.agent_runtime.executor import StepObservation, execute_plan
from app.agent_runtime.planner import (
    AgentPlan,
    AgentRequest,
    PlanValidationError,
    PlannedStep,
    build_plan,
    infer_intent,
    parse_plan,
    resolve_context,
)
from app.agent_runtime.registry import ToolRegistry, build_registry
from app.agent_runtime.store import AgentSessionStore, agent_store
from app.observability import record_span, trace_scope
from app.schemas.contracts import BusinessState
from app.state import load_business_state

FAILURE_TAXONOMY: dict[str, str] = {
    "retrieval_miss": "retrieval_miss",
    "citation_out_of_force": "retrieval_miss",
    "unsupported_citation": "hallucination",
    "inconsistent_figures": "reasoning_error",
    "missing_identifier": "reasoning_error",
    "plan_coverage": "reasoning_error",
    "tool_error": "tool_call_error",
    "not_found": "tool_call_error",
    "invalid_argument": "tool_call_error",
    "malformed_arguments": "tool_call_error",
    "unknown_tool": "tool_call_error",
    "internal_error": "tool_call_error",
    "policy_unavailable": "tool_call_error",
    "loop_guard": "tool_call_error",
    "step_cap": "tool_call_error",
    "token_cap": "tool_call_error",
    "time_cap": "tool_call_error",
    "budget_exhausted": "tool_call_error",
    "malformed_json": "tool_call_error",
    "invalid_plan": "tool_call_error",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latest(observations: list[StepObservation]) -> list[StepObservation]:
    latest: dict[str, StepObservation] = {}
    for observation in observations:
        latest[observation.step_id] = observation
    return list(latest.values())


def _citations(observations: list[StepObservation]) -> list[dict]:
    for observation in reversed(observations):
        if observation.tool == "policy_search" and observation.status == "ok":
            return list(observation.output.get("hits") or [])
    return []


def _retry_plan(plan: AgentPlan, retry_ids: set[str], question: str, intent: str) -> AgentPlan:
    steps = []
    for step in plan.steps:
        if step.step_id not in retry_ids:
            continue
        args = dict(step.args)
        if step.tool == "policy_search":
            args["query"] = f"{args.get('query', question)} {intent.replace('_', ' ')}".strip()
            args["top_k"] = max(int(args.get("top_k", 3)), 5)
        steps.append(PlannedStep(step_id=step.step_id, tool=step.tool, args=args, purpose=step.purpose))
    return AgentPlan(goal=plan.goal, intent=plan.intent, steps=steps, source="critic_retry")


@dataclass
class AgentRun:
    run_id: str
    conversation_id: str
    turn: int
    intent: str
    question: str
    status: str
    plan: AgentPlan
    clarifications: list[str]
    observations: list[StepObservation]
    critique: Critique
    retries: dict
    budget: dict
    usage: dict
    failure_labels: list[str]
    citations: list[dict]
    context: dict
    plan_source: str
    created_at: str = field(default_factory=_now)

    def taxonomy(self) -> dict[str, str]:
        return {label: FAILURE_TAXONOMY.get(label, "reasoning_error") for label in self.failure_labels}

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "conversation_id": self.conversation_id,
            "turn": self.turn,
            "intent": self.intent,
            "question": self.question,
            "status": self.status,
            "plan": {**self.plan.to_dict(), "source": self.plan_source},
            "clarifications": self.clarifications,
            "steps": [observation.to_dict() for observation in _latest(self.observations)],
            "attempts": [observation.to_dict() for observation in self.observations],
            "critique": self.critique.to_dict(),
            "retries": self.retries,
            "budget": self.budget,
            "usage": self.usage,
            "failure_labels": self.failure_labels,
            "failure_taxonomy": self.taxonomy(),
            "citations": self.citations,
            "context": self.context,
            "side_effects": False,
            "created_at": self.created_at,
        }


def run_review(
    request: AgentRequest,
    *,
    state: BusinessState | None = None,
    data_dir: Path | None = None,
    registry: ToolRegistry | None = None,
    store: AgentSessionStore | None = None,
    budget: AgentBudget | None = None,
) -> AgentRun:
    """Plan, execute and critique one review. Read-only, bounded and deterministic."""
    started = time.monotonic()
    state = state or load_business_state(data_dir=data_dir, expected_version=request.state_version)
    registry = registry or build_registry(state, data_dir)
    store = store or agent_store
    conversation_id = request.conversation_id or f"conv-{uuid4().hex[:10]}"
    stored = store.context(conversation_id) if request.conversation_id else {}
    merged = resolve_context(request, stored)
    intent = merged.get("intent") or infer_intent(request.question, merged.get("sku_id"))
    turn = store.next_turn(conversation_id)

    labels: list[str] = []
    plan_source = "deterministic"
    plan, clarifications = build_plan(request, merged, state)
    if request.plan:
        try:
            plan = parse_plan(request.plan, registry)
            plan_source = "supplied"
        except PlanValidationError as exc:
            labels.append(exc.code)
            plan_source = "deterministic_fallback"
            record_span("agent_plan_fallback", "fallback", error=exc.message, detail={"code": exc.code})

    budget = budget or AgentBudget()
    with trace_scope(f"agent:{conversation_id}", source="agent"):
        record_span(
            "agent_plan",
            "agent",
            detail={"intent": intent, "source": plan_source, "steps": [step.tool for step in plan.steps]},
        )
        observations = execute_plan(plan, registry, budget, state)
        review = critique(plan, observations, state, clarifications)

        retry_ids = review.retry_step_ids()
        retries = {"rounds": 0, "step_ids": []}
        if retry_ids:
            retries = {"rounds": 1, "step_ids": sorted(retry_ids)}
            signatures: dict[str, int] = {}
            retry_plan = _retry_plan(plan, retry_ids, request.question, intent)
            retried = execute_plan(
                retry_plan,
                registry,
                budget,
                state,
                attempt=2,
                observations=observations,
                signature_counts=signatures,
            )
            observations = [*observations, *retried]
            review = critique(plan, observations, state, clarifications)

        if not review.passed:
            status = "failed"
        elif clarifications:
            status = "needs_clarification"
        else:
            status = "ok"

        findings = review.findings
        for finding in findings:
            if finding.code not in labels:
                labels.append(finding.code)
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        tool_calls = sum(1 for observation in observations if observation.status != "skipped")
        usage = {
            "tool_calls": tool_calls,
            "retries": retries["rounds"],
            "estimated_tokens": budget.estimated_tokens,
            "token_basis": TOKEN_ESTIMATE_BASIS,
            "elapsed_ms": elapsed_ms,
            "citations": len(_citations(observations)),
        }
        citations = _citations(observations)
        context_out = {key: value for key, value in merged.items() if value is not None}
        run = AgentRun(
            run_id=f"run-{uuid4().hex[:12]}",
            conversation_id=conversation_id,
            turn=turn,
            intent=intent,
            question=request.question,
            status=status,
            plan=plan,
            clarifications=clarifications,
            observations=observations,
            critique=review,
            retries=retries,
            budget=budget.snapshot(),
            usage=usage,
            failure_labels=labels,
            citations=citations,
            context=context_out,
            plan_source=plan_source,
        )
        record_span(
            "agent_critique",
            "agent",
            status="ok" if review.passed else "error",
            error=None if review.passed else ", ".join(sorted({finding.code for finding in findings})),
            detail={"retry_step_ids": sorted(retry_ids), "findings": len(findings)},
        )
        record_span(
            "agent_run",
            "agent",
            status="ok" if status != "failed" else "error",
            latency_ms=elapsed_ms,
            detail={
                "intent": intent,
                "status": status,
                "tool_calls": tool_calls,
                "retries": retries["rounds"],
                "failure_labels": labels,
                "steps": [step.tool for step in plan.steps],
            },
        )

    store.save_turn(
        run_id=run.run_id,
        conversation_id=conversation_id,
        turn=turn,
        question=request.question,
        intent=intent,
        status=status,
        context=context_out,
        summary={
            "failure_labels": labels,
            "citations": [citation["document_id"] for citation in citations],
            "tool_calls": usage["tool_calls"],
            "retries": retries["rounds"],
            "estimated_tokens": usage["estimated_tokens"],
            "elapsed_ms": elapsed_ms,
        },
    )
    return run
