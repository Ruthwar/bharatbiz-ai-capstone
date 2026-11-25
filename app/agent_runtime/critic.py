"""Deterministic critic for one agent run.

The critic checks the run, not the prose: every planned step ran, no tool failed, the
review has at least one usable citation with a verbatim quote and a licence, and every
figure the tools returned is internally consistent. It marks a small set of findings as
retryable; the runtime grants one retry round and then reports what is still wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.agent_runtime.executor import StepObservation
from app.agent_runtime.planner import AgentPlan
from app.schemas.contracts import BusinessState

RETRYABLE_CODES = {"retrieval_miss", "internal_error", "policy_unavailable"}


@dataclass
class Finding:
    code: str
    message: str
    step_ids: list[str] = field(default_factory=list)
    severity: str = "error"
    retryable: bool = False

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "step_ids": self.step_ids,
            "severity": self.severity,
            "retryable": self.retryable,
        }


@dataclass
class Critique:
    passed: bool
    findings: list[Finding] = field(default_factory=list)

    def codes(self) -> list[str]:
        return [finding.code for finding in self.findings]

    def retry_step_ids(self) -> set[str]:
        return {
            step_id
            for finding in self.findings
            if finding.severity == "error" and finding.retryable
            for step_id in finding.step_ids
        }

    def to_dict(self) -> dict:
        return {"passed": self.passed, "findings": [finding.to_dict() for finding in self.findings]}


def _latest(observations: list[StepObservation]) -> dict[str, StepObservation]:
    latest: dict[str, StepObservation] = {}
    for observation in observations:
        latest[observation.step_id] = observation
    return latest


def _decimal(value) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _citation_findings(observation: StepObservation, as_of: date, applicable: set[str] | None) -> list[Finding]:
    hits = observation.output.get("hits") or []
    findings: list[Finding] = []
    if not hits:
        findings.append(
            Finding(
                code="retrieval_miss",
                message="No policy passage was retrieved for the review question.",
                step_ids=[observation.step_id],
                retryable=True,
            )
        )
        return findings
    if applicable and not any(hit.get("document_id") in applicable for hit in hits):
        findings.append(
            Finding(
                code="retrieval_miss",
                message="Retrieved passages are outside the policy set that applies to this event.",
                step_ids=[observation.step_id],
                retryable=True,
            )
        )
    for hit in hits:
        document_id = hit.get("document_id") or "unknown"
        if not hit.get("quote") or not hit.get("licence") or not hit.get("effective_from"):
            findings.append(
                Finding(
                    code="unsupported_citation",
                    message=f"{document_id} was cited without a quote, licence or effective date.",
                    step_ids=[observation.step_id],
                )
            )
            continue
        try:
            effective = date.fromisoformat(hit["effective_from"])
        except (TypeError, ValueError):
            effective = None
        if effective is None or effective > as_of:
            findings.append(
                Finding(
                    code="citation_out_of_force",
                    message=f"{document_id} is not in force on the decision date ({as_of.isoformat()}).",
                    step_ids=[observation.step_id],
                )
            )
    return findings


def _figure_findings(latest: dict[str, StepObservation]) -> list[Finding]:
    findings: list[Finding] = []

    inventory = next(
        (obs for obs in latest.values() if obs.tool == "inventory_position" and obs.status == "ok"), None
    )
    orders = next((obs for obs in latest.values() if obs.tool == "open_orders" and obs.status == "ok"), None)
    if inventory:
        proposal = inventory.output.get("proposal") or {}
        available = proposal.get("available_units")
        atp = proposal.get("atp_units")
        immediate = proposal.get("immediately_available_units")
        values = (available, atp, immediate)
        if any(not isinstance(value, int) or value < 0 for value in values):
            findings.append(
                Finding(
                    code="inconsistent_figures",
                    message="Inventory availability contains a negative or non-integer quantity.",
                    step_ids=[inventory.step_id],
                )
            )
        elif immediate > atp:
            findings.append(
                Finding(
                    code="inconsistent_figures",
                    message="Immediately available units exceed availability-to-promise.",
                    step_ids=[inventory.step_id],
                )
            )
    if orders:
        rows = orders.output.get("orders") or []
        total = orders.output.get("total_requested_units")
        if isinstance(total, int) and total != sum(int(row.get("quantity_units", 0)) for row in rows):
            findings.append(
                Finding(
                    code="inconsistent_figures",
                    message="Order total does not equal the sum of the listed order quantities.",
                    step_ids=[orders.step_id],
                )
            )
    if inventory and orders:
        demand = (inventory.output.get("proposal") or {}).get("open_demand_units")
        total = orders.output.get("total_requested_units")
        if isinstance(demand, int) and isinstance(total, int) and demand != total:
            findings.append(
                Finding(
                    code="inconsistent_figures",
                    message="Inventory demand baseline differs from the open-order total.",
                    step_ids=[inventory.step_id, orders.step_id],
                )
            )

    cash = next((obs for obs in latest.values() if obs.tool == "cash_position" and obs.status == "ok"), None)
    if cash:
        ending = _decimal(cash.output.get("ending_cash_rupees"))
        buffer = _decimal(cash.output.get("minimum_buffer_rupees"))
        headroom = _decimal(cash.output.get("headroom_rupees"))
        feasible = cash.output.get("feasible")
        if ending is None or buffer is None or headroom is None:
            findings.append(
                Finding(
                    code="inconsistent_figures",
                    message="Cash projection is missing a rupee amount.",
                    step_ids=[cash.step_id],
                )
            )
        elif headroom != ending - buffer or feasible != (headroom >= 0):
            findings.append(
                Finding(
                    code="inconsistent_figures",
                    message="Cash headroom or feasibility disagrees with ending cash and the buffer.",
                    step_ids=[cash.step_id],
                )
            )

    suppliers = next(
        (obs for obs in latest.values() if obs.tool == "supplier_options" and obs.status == "ok"), None
    )
    if suppliers:
        for option in suppliers.output.get("options") or []:
            quantity = option.get("quantity_units")
            unit_cost = _decimal(option.get("unit_cost_rupees"))
            total_cost = _decimal(option.get("total_cost_rupees"))
            if not isinstance(quantity, int) or quantity < 0 or unit_cost is None or total_cost is None:
                findings.append(
                    Finding(
                        code="inconsistent_figures",
                        message="A supplier option carries a negative quantity or a missing cost.",
                        step_ids=[suppliers.step_id],
                    )
                )
                break
            if total_cost != unit_cost * quantity:
                findings.append(
                    Finding(
                        code="inconsistent_figures",
                        message="A supplier option total does not equal quantity times unit cost.",
                        step_ids=[suppliers.step_id],
                    )
                )
                break
    return findings


def critique(
    plan: AgentPlan,
    observations: list[StepObservation],
    state: BusinessState,
    clarifications: list[str] | None = None,
) -> Critique:
    latest = _latest(observations)
    findings: list[Finding] = []

    for step in plan.steps:
        observation = latest.get(step.step_id)
        if observation is None:
            findings.append(
                Finding(
                    code="plan_coverage",
                    message=f"Planned step {step.step_id} ({step.tool}) did not run.",
                    step_ids=[step.step_id],
                )
            )
        elif observation.status == "skipped":
            findings.append(
                Finding(
                    code=observation.code or "budget_exhausted",
                    message=f"Planned step {step.step_id} ({step.tool}) was skipped: {observation.error}",
                    step_ids=[step.step_id],
                )
            )

    for observation in latest.values():
        if observation.status != "error":
            continue
        findings.append(
            Finding(
                code=observation.code or "tool_error",
                message=f"{observation.tool} failed: {observation.error}",
                step_ids=[observation.step_id],
                retryable=(observation.code or "") in RETRYABLE_CODES,
            )
        )

    as_of = state.as_of.date()
    if not any(step.tool == "policy_search" for step in plan.steps):
        findings.append(
            Finding(
                code="plan_coverage",
                message="Plan has no policy_search step; a review must cite applicable policy.",
            )
        )
    metadata = next(
        (obs for obs in latest.values() if obs.tool == "policy_metadata" and obs.status == "ok"), None
    )
    applicable = set((metadata.output.get("applicable") or [])) if metadata else None
    for observation in latest.values():
        if observation.tool == "policy_search" and observation.status == "ok":
            findings.extend(_citation_findings(observation, as_of, applicable))

    findings.extend(_figure_findings(latest))

    for clarification in clarifications or []:
        findings.append(
            Finding(code="missing_identifier", message=clarification, severity="needs_input")
        )

    passed = not any(finding.severity == "error" for finding in findings)
    return Critique(passed=passed, findings=findings)
