"""OR-Tools CP-SAT selector for the same objective as deterministic ranking.

The solver chooses one already-built candidate. It does not invent quantities, prices,
or dates. An empty feasible set is reported as INFEASIBLE.
"""

from ortools.sat.python import cp_model

from app.optimization.baseline import rank_key
from app.schemas.contracts import CandidatePlan


def _solve(model: cp_model.CpModel) -> tuple[cp_model.CpSolver, int]:
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 1
    return solver, solver.Solve(model)


def _prove_infeasible() -> str:
    model = cp_model.CpModel()
    rejected = model.NewBoolVar("rejected")
    model.Add(rejected == 0)
    model.Add(rejected == 1)
    solver, status = _solve(model)
    return solver.StatusName(status)


def select_best_plan_ortools(plans: list[CandidatePlan]) -> tuple[CandidatePlan | None, str]:
    if not plans:
        return None, _prove_infeasible()

    model = cp_model.CpModel()
    choices = [model.NewBoolVar(f"plan_{index}") for index in range(len(plans))]
    model.Add(sum(choices) == 1)
    keys = [rank_key(plan) for plan in plans]
    id_order = {plan.candidate_id: index for index, plan in enumerate(sorted(plans, key=lambda row: row.candidate_id))}
    objectives = []
    for position in range(4):
        upper = max(key[position] for key in keys)
        target = model.NewIntVar(0, upper, f"objective_{position}")
        model.Add(target == sum(choice * keys[index][position] for index, choice in enumerate(choices)))
        objectives.append(target)
    id_target = model.NewIntVar(0, max(id_order.values()), "objective_id")
    model.Add(id_target == sum(choice * id_order[plan.candidate_id] for choice, plan in zip(choices, plans)))
    objectives.append(id_target)

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 1
    for target in objectives:
        model.Minimize(target)
        status = solver.Solve(model)
        if status != cp_model.OPTIMAL:
            return None, solver.StatusName(status)
        model.Add(target == solver.Value(target))

    chosen = [plan for choice, plan in zip(choices, plans) if solver.Value(choice) == 1]
    if len(chosen) != 1:
        return None, "INFEASIBLE"
    return chosen[0], "OPTIMAL"
