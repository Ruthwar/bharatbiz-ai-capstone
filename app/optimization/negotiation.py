"""Negotiation surface for specialist proposals.

Returns the selected plan, the other feasible plans, the excluded options, and the
tradeoff against the published objective. OR-Tools and the deterministic ranker
see the same candidates. Neither one is allowed to change quantities or prices.
"""

from dataclasses import dataclass

from app.optimization.baseline import select_best_plan
from app.optimization.ortools_selector import select_best_plan_ortools
from app.schemas.contracts import CandidateExclusion, CandidatePlan

OBJECTIVE = (
    "Minimize unmet units, then late units, then arrival date, then cost, then candidate id. "
    "Service is the first objective, not a hard fill-rate. "
    "Supplier minimum order, capacity, lead time, and the cash buffer are hard constraints."
)


@dataclass(frozen=True)
class Negotiation:
    status: str
    objective: str
    selected: CandidatePlan | None
    deterministic_candidate_id: str | None
    ortools_candidate_id: str | None
    planners_agree: bool
    ortools_status: str
    tradeoffs: tuple[str, ...]
    constraint_checks: tuple[str, ...]
    infeasibility_reasons: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "objective": self.objective,
            "selected_candidate_id": self.selected.candidate_id if self.selected else None,
            "deterministic_candidate_id": self.deterministic_candidate_id,
            "ortools_candidate_id": self.ortools_candidate_id,
            "planners_agree": self.planners_agree,
            "ortools_status": self.ortools_status,
            "tradeoffs": list(self.tradeoffs),
            "constraint_checks": list(self.constraint_checks),
            "infeasibility_reasons": list(self.infeasibility_reasons),
        }


def _money(value) -> str:
    return f"{value:+.2f}"


def _tradeoff(selected: CandidatePlan, other: CandidatePlan) -> str:
    cost_delta = other.total_cost_rupees - selected.total_cost_rupees
    return (
        f"{other.candidate_id} compared with {selected.candidate_id}: "
        f"{other.unmet_units - selected.unmet_units:+d} unmet, "
        f"{other.late_units - selected.late_units:+d} late, "
        f"{_money(cost_delta)} rupees."
    )


def _reasons(exclusions: list[CandidateExclusion]) -> tuple[str, ...]:
    return tuple(
        f"{exclusion.candidate_id}: {', '.join(exclusion.reasons)}"
        for exclusion in exclusions
    )


def negotiate(
    plans: list[CandidatePlan],
    exclusions: list[CandidateExclusion] | None = None,
) -> Negotiation:
    exclusions = list(exclusions or [])
    deterministic = select_best_plan(plans) if plans else None
    ortools_plan, ortools_status = select_best_plan_ortools(plans)
    deterministic_id = deterministic.candidate_id if deterministic else None
    ortools_id = ortools_plan.candidate_id if ortools_plan else None
    reasons = _reasons(exclusions) if deterministic is None else ()
    if deterministic is None and not reasons:
        reasons = ("no_feasible_candidate",)
    checks = []
    if deterministic is not None:
        checks.append(
            f"Selected {deterministic.candidate_id} satisfies stock, supplier minimum order, "
            "capacity, lead time, and the cash buffer."
        )
    checks.append(
        "Service is minimized unmet units. A partial plan stays feasible when no covering purchase passes the hard constraints."
    )
    checks.extend(f"Excluded {reason}." for reason in _reasons(exclusions))
    tradeoffs = tuple(_tradeoff(deterministic, other) for other in plans if other.candidate_id != deterministic.candidate_id) if deterministic else ()
    return Negotiation(
        status="feasible" if deterministic is not None else "infeasible",
        objective=OBJECTIVE,
        selected=deterministic,
        deterministic_candidate_id=deterministic_id,
        ortools_candidate_id=ortools_id,
        planners_agree=deterministic_id == ortools_id,
        ortools_status=ortools_status,
        tradeoffs=tradeoffs,
        constraint_checks=tuple(checks),
        infeasibility_reasons=reasons,
    )
