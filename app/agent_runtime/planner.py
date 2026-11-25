"""Deterministic planning plus strict validation for a supplied plan.

The default planner is rules, not a model: the same request always yields the same ordered
steps. A supplied plan (for example a small model's JSON proposal) is validated against the
registry before anything runs; malformed JSON, unknown tools and bad arguments are reported
as labels and fall back to the deterministic plan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.agent_runtime.registry import ToolError, ToolRegistry
from app.agent_runtime.store import CONTEXT_FIELDS
from app.schemas.contracts import BusinessState

MAX_PLAN_STEPS = 10

OPERATIONAL_INTENTS = (
    "baseline",
    "demand_spike",
    "supplier_delay",
    "limited_cash",
    "stock_discrepancy",
    "dispatch_planning",
)
RETAILER_INTENTS = (
    "delivery_complaint",
    "damaged_item",
    "missing_item",
    "product_request",
    "credit_check",
    "scheme_claim",
    "delivery_discrepancy",
)

_INTENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("batch_recall", ("recall", "withdraw batch")),
    ("short_dated_stock", ("short dated", "near expiry", "expiry", "expiring", "shelf life")),
    ("scheme_claim", ("scheme", "claim window", "reimbursement")),
    ("credit_check", ("credit", "outstanding", "overdue")),
    ("damaged_item", ("damaged", "crushed", "broken carton")),
    ("missing_item", ("missing", "not in the case", "short delivery")),
    ("delivery_complaint", ("complaint", "did not arrive", "late delivery")),
    ("dispatch_planning", ("dispatch", "route", "load plan")),
    ("competitor_observation", ("competitor", "rival offer")),
    ("product_request", ("new product", "list a product", "product request")),
    ("supplier_delay", ("supplier delay", "delayed", "delay", "revision")),
    ("limited_cash", ("cash", "liquidity", "afford", "headroom")),
    ("demand_spike", ("spike", "surge", "uplift", "higher demand")),
)


@dataclass
class AgentRequest:
    question: str
    conversation_id: str | None = None
    intent: str | None = None
    sku_id: str | None = None
    supplier_id: str | None = None
    retailer_id: str | None = None
    delay_days: int | None = None
    required_units: int | None = None
    outflow_rupees: str | None = None
    state_version: str | None = None
    plan: dict | str | None = None

    def as_context(self) -> dict:
        return {
            key: getattr(self, key)
            for key in CONTEXT_FIELDS
            if getattr(self, key) is not None
        }


@dataclass(frozen=True)
class PlannedStep:
    step_id: str
    tool: str
    args: dict
    purpose: str = ""

    def to_dict(self) -> dict:
        return {"step_id": self.step_id, "tool": self.tool, "args": self.args, "purpose": self.purpose}


@dataclass
class AgentPlan:
    goal: str
    intent: str
    steps: list[PlannedStep] = field(default_factory=list)
    source: str = "deterministic"

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "intent": self.intent,
            "source": self.source,
            "steps": [step.to_dict() for step in self.steps],
        }


class PlanValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def infer_intent(question: str, sku_id: str | None) -> str:
    lowered = question.lower()
    for intent, keywords in _INTENT_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return intent
    return "baseline" if sku_id else "unclassified"


def resolve_context(request: AgentRequest, stored: dict | None) -> dict:
    """Request values win; the persisted turn supplies anything the caller omitted."""
    merged = {key: (stored or {}).get(key) for key in CONTEXT_FIELDS}
    merged.update(request.as_context())
    if not merged.get("intent"):
        merged["intent"] = infer_intent(request.question, merged.get("sku_id"))
    return merged


def build_plan(request: AgentRequest, context: dict, state: BusinessState) -> tuple[AgentPlan, list[str]]:
    intent = context.get("intent") or infer_intent(request.question, context.get("sku_id"))
    sku_id = context.get("sku_id")
    supplier_id = context.get("supplier_id")
    retailer_id = context.get("retailer_id")
    delay_days = context.get("delay_days")
    outflow = context.get("outflow_rupees")

    steps: list[PlannedStep] = []
    clarifications: list[str] = []

    def add(tool: str, args: dict, purpose: str) -> None:
        steps.append(PlannedStep(step_id=f"s{len(steps) + 1}", tool=tool, args=args, purpose=purpose))

    add(
        "policy_metadata",
        {"event_type": intent, "supplier_id": supplier_id},
        "Check which policy documents apply to this event, party and decision date.",
    )
    add(
        "policy_search",
        {
            "query": request.question,
            "top_k": 3,
            "supplier_id": supplier_id,
            "doc_types": ["policy", "sop"],
            "event_type": intent,
        },
        "Retrieve verbatim policy and procedure passages for the reviewer.",
    )

    if sku_id:
        delayed = "all" if intent == "supplier_delay" else 0
        add(
            "inventory_position",
            {"sku_id": sku_id, "delayed_incoming_units": delayed},
            "Read usable stock and incoming units for the SKU.",
        )
        add("open_orders", {"sku_id": sku_id}, "Read open orders that compete for the same stock.")
    elif intent in OPERATIONAL_INTENTS:
        clarifications.append("Provide a SKU (and pack) so stock and open orders can be checked.")

    if sku_id and supplier_id and delay_days is not None:
        add(
            "supplier_options",
            {
                "sku_id": sku_id,
                "required_units": context.get("required_units") if context.get("required_units") is not None else "auto",
                "original_supplier_id": supplier_id,
                "delay_days": delay_days,
                "planning_horizon": "auto",
            },
            "Read supplier offers for the uncovered quantity; no order is placed.",
        )
    elif intent == "supplier_delay":
        if not supplier_id:
            clarifications.append("Provide the delayed supplier's ID.")
        if delay_days is None:
            clarifications.append("Provide the expected delay in days.")

    if retailer_id:
        add("retailer_profile", {"retailer_id": retailer_id}, "Read the retailer record and open allocations.")
    elif intent in RETAILER_INTENTS:
        clarifications.append("Provide the retailer account ID.")

    if outflow is not None or intent == "limited_cash":
        add(
            "cash_position",
            {"outflow_rupees": outflow if outflow is not None else "0"},
            "Project ending cash and headroom after the immediate outflow.",
        )

    if len(steps) > MAX_PLAN_STEPS:  # pragma: no cover - the planner cannot currently exceed this
        raise PlanValidationError("step_cap", f"plan has {len(steps)} steps; the cap is {MAX_PLAN_STEPS}")
    goal = f"Ground the {intent.replace('_', ' ')} review in state, orders and applicable policy."
    return AgentPlan(goal=goal, intent=intent, steps=steps), clarifications


def parse_plan(payload: dict | str, registry: ToolRegistry) -> AgentPlan:
    """Validate a supplied plan. Anything unexpected is a labelled rejection, never a crash."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise PlanValidationError("malformed_json", f"plan is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise PlanValidationError("invalid_plan", "plan must be a JSON object")
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise PlanValidationError("invalid_plan", "plan.steps must be a non-empty array")
    if len(raw_steps) > MAX_PLAN_STEPS:
        raise PlanValidationError("step_cap", f"plan has {len(raw_steps)} steps; the cap is {MAX_PLAN_STEPS}")

    steps: list[PlannedStep] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            raise PlanValidationError("invalid_plan", f"step {index} is not an object")
        tool = raw.get("tool")
        if not isinstance(tool, str) or not tool:
            raise PlanValidationError("invalid_plan", f"step {index} has no tool name")
        if tool not in registry.names():
            raise PlanValidationError("unknown_tool", f"step {index} names an unknown tool: {tool}")
        arguments = raw.get("args", {})
        try:
            cleaned = registry.validate_arguments(tool, arguments)
        except ToolError as exc:
            raise PlanValidationError(exc.code, f"step {index} ({tool}): {exc.message}") from exc
        step_id = raw.get("step_id") or f"s{index}"
        if not isinstance(step_id, str) or not step_id or step_id in seen:
            raise PlanValidationError("invalid_plan", f"step {index} has a missing or duplicate step_id")
        seen.add(step_id)
        purpose = raw.get("purpose") if isinstance(raw.get("purpose"), str) else ""
        steps.append(PlannedStep(step_id=step_id, tool=tool, args=cleaned, purpose=purpose))

    intent = payload.get("intent") if isinstance(payload.get("intent"), str) else "unclassified"
    goal = payload.get("goal") if isinstance(payload.get("goal"), str) else f"Execute the supplied {intent} plan."
    return AgentPlan(goal=goal, intent=intent, steps=steps, source="supplied")
