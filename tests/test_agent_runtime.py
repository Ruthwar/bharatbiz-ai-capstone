import pytest
from fastapi.testclient import TestClient

from app.agent_runtime import (
    AgentBudget,
    AgentRequest,
    AgentSessionStore,
    ToolError,
    ToolRegistry,
    ToolSpec,
    build_plan,
    build_registry,
    parse_plan,
    resolve_context,
    run_review,
)
from app.agent_runtime.planner import PlanValidationError
from app.agent_runtime.runtime import agent_store
from app.main import app
from app.observability import reset_traces, trace_store
from app.store.ledger import ledger

client = TestClient(app)

QUESTION = "The supplier says the cooking oil delivery is delayed by two days; what can we commit?"
SKU = "SKU-003"
SUPPLIER = "SUP-005"
RETAILER = "RET-017"


@pytest.fixture(autouse=True)
def clean_agent_state():
    agent_store.reset()
    reset_traces()
    ledger.reset()
    yield
    agent_store.reset()
    reset_traces()
    ledger.reset()


@pytest.fixture
def demo_request():
    return AgentRequest(
        question=QUESTION,
        sku_id=SKU,
        supplier_id=SUPPLIER,
        delay_days=2,
        intent="supplier_delay",
    )


def test_registry_exposes_only_read_only_tools(state):
    registry = build_registry(state)

    assert set(registry.names()) == {
        "policy_search",
        "policy_metadata",
        "inventory_position",
        "open_orders",
        "supplier_options",
        "cash_position",
        "retailer_profile",
    }
    assert len(registry.names()) >= 3
    assert all(spec["read_only"] for spec in registry.describe())


def test_registry_rejects_unknown_tools_and_arguments(state):
    registry = build_registry(state)

    with pytest.raises(ToolError) as unknown:
        registry.call("delete_stock", {})
    assert unknown.value.code == "unknown_tool"

    with pytest.raises(ToolError) as extra:
        registry.call("inventory_position", {"sku_id": SKU, "write": True})
    assert extra.value.code == "malformed_arguments"

    with pytest.raises(ToolError) as missing:
        registry.call("inventory_position", {})
    assert missing.value.code == "malformed_arguments"


def test_tool_calls_are_deterministic_and_do_not_touch_the_review_queue(state):
    registry = build_registry(state)
    before = len(ledger.pending_reviews())

    first = registry.call("open_orders", {"sku_id": SKU})
    second = registry.call("open_orders", {"sku_id": SKU})

    assert first.status == second.status == "ok"
    assert first.output == second.output
    assert len(ledger.pending_reviews()) == before


def test_planner_builds_the_expected_steps_in_a_fixed_order(state, demo_request):
    demo_request.retailer_id = RETAILER
    demo_request.outflow_rupees = "5000"
    context = resolve_context(demo_request, {})

    plan, clarifications = build_plan(demo_request, context, state)

    assert clarifications == []
    assert [step.tool for step in plan.steps] == [
        "policy_metadata",
        "policy_search",
        "inventory_position",
        "open_orders",
        "supplier_options",
        "retailer_profile",
        "cash_position",
    ]
    assert plan.steps[0].args["event_type"] == "supplier_delay"
    assert plan.steps[4].args["required_units"] == "auto"
    assert plan.steps[4].args["planning_horizon"] == "auto"


def test_planner_asks_for_missing_identifiers_instead_of_inventing_them(state):
    request = AgentRequest(question="The supplier delay is worse than expected.", intent="supplier_delay")

    plan, clarifications = build_plan(request, resolve_context(request, {}), state)

    assert [step.tool for step in plan.steps] == ["policy_metadata", "policy_search"]
    assert any("SKU" in item for item in clarifications)
    assert any("supplier" in item for item in clarifications)
    assert any("delay" in item for item in clarifications)


def test_default_run_is_grounded_and_bounded(state, demo_request):
    demo_request.conversation_id = "conv-grounded"

    run = run_review(demo_request, store=AgentSessionStore(":memory:"))
    result = run.to_dict()

    assert result["status"] == "ok"
    assert result["side_effects"] is False
    assert result["plan"]["source"] == "deterministic"
    assert result["retries"]["rounds"] <= 1
    assert any(citation["document_id"] == "POL-DLY-001" for citation in result["citations"])
    assert all(citation["licence"] for citation in result["citations"])
    assert result["budget"]["steps"] <= result["budget"]["max_steps"]
    assert result["usage"]["estimated_tokens"] <= result["budget"]["max_estimated_tokens"]


def test_malformed_json_plan_falls_back_to_the_deterministic_plan(state, demo_request):
    demo_request.plan = "{this is not json"
    demo_request.conversation_id = "conv-malformed"

    result = run_review(demo_request, store=AgentSessionStore(":memory:")).to_dict()

    assert result["plan"]["source"] == "deterministic_fallback"
    assert "malformed_json" in result["failure_labels"]
    assert result["failure_taxonomy"]["malformed_json"] == "tool_call_error"
    assert result["status"] == "ok"


def test_supplied_plan_validation_reports_codes_without_running(state):
    registry = build_registry(state)

    with pytest.raises(PlanValidationError) as malformed:
        parse_plan("{bad", registry)
    assert malformed.value.code == "malformed_json"

    with pytest.raises(PlanValidationError) as unknown:
        parse_plan({"steps": [{"tool": "drop_tables", "args": {}}]}, registry)
    assert unknown.value.code == "unknown_tool"

    with pytest.raises(PlanValidationError) as too_many:
        parse_plan(
            {"steps": [{"tool": "policy_search", "args": {"query": "x"}} for _ in range(11)]},
            registry,
        )
    assert too_many.value.code == "step_cap"

    valid = parse_plan({"steps": [{"tool": "policy_search", "args": {"query": "delay notice"}}]}, registry)
    assert valid.source == "supplied"
    assert valid.steps[0].step_id == "s1"


def test_step_budget_stops_execution_and_labels_the_run(state, demo_request):
    result = run_review(
        demo_request,
        store=AgentSessionStore(":memory:"),
        budget=AgentBudget(max_steps=2),
    ).to_dict()

    assert result["budget"]["steps"] == 2
    assert result["usage"]["tool_calls"] == 2
    assert any(step["status"] == "skipped" for step in result["steps"])
    assert "step_cap" in result["failure_labels"]
    assert result["failure_taxonomy"]["step_cap"] == "tool_call_error"
    assert result["status"] == "failed"


def test_token_budget_stops_execution(state, demo_request):
    result = run_review(
        demo_request,
        store=AgentSessionStore(":memory:"),
        budget=AgentBudget(max_estimated_tokens=10),
    ).to_dict()

    assert result["budget"]["estimated_tokens"] > 10
    assert result["usage"]["tool_calls"] == 1
    assert "token_cap" in result["failure_labels"]


def test_loop_guard_refuses_a_repeated_identical_call(state):
    plan = {
        "intent": "baseline",
        "steps": [
            {"step_id": "s1", "tool": "open_orders", "args": {"sku_id": SKU}},
            {"step_id": "s2", "tool": "open_orders", "args": {"sku_id": SKU}},
            {"step_id": "s3", "tool": "open_orders", "args": {"sku_id": SKU}},
            {"step_id": "s4", "tool": "open_orders", "args": {"sku_id": SKU}},
            {"step_id": "s5", "tool": "policy_search", "args": {"query": "delivery delay notice"}},
        ],
    }
    result = run_review(
        AgentRequest(question="Check the same orders repeatedly.", plan=plan),
        store=AgentSessionStore(":memory:"),
    ).to_dict()

    by_step = {step["step_id"]: step for step in result["steps"]}
    assert by_step["s1"]["status"] == by_step["s2"]["status"] == "ok"
    assert by_step["s3"]["code"] == by_step["s4"]["code"] == "loop_guard"
    assert "loop_guard" in result["failure_labels"]
    assert result["status"] == "failed"


def test_critic_retry_recovers_when_the_second_attempt_returns_a_citation(state):
    calls = {"count": 0}
    citation = {
        "document_id": "POL-DLY-001",
        "title": "Delivery policy",
        "section": "Rules",
        "quote": "A revised delivery date must be confirmed in writing.",
        "effective_from": "2026-01-01",
        "version": "1",
        "licence": "CC0-1.0 (synthetic)",
        "classification": "synthetic",
        "score": 1.0,
    }

    def search(query: str, top_k: int = 3) -> dict:
        calls["count"] += 1
        hits = [] if calls["count"] == 1 else [citation]
        return {"query": query, "hits": hits, "miss": not hits}

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="policy_search",
            description="stub",
            parameters={
                "query": {"type": "str", "required": True},
                "top_k": {"type": "int", "required": False},
            },
            handler=search,
        )
    )
    result = run_review(
        AgentRequest(
            question="Summarise the supplier onboarding policy.",
            plan={"steps": [{"step_id": "s1", "tool": "policy_search", "args": {"query": "onboarding"}}]},
        ),
        state=state,
        registry=registry,
        store=AgentSessionStore(":memory:"),
    ).to_dict()

    assert calls["count"] == 2
    assert result["retries"] == {"rounds": 1, "step_ids": ["s1"]}
    assert result["status"] == "ok"
    assert result["failure_labels"] == []


def test_tool_failure_is_recorded_not_raised(state):
    result = run_review(
        AgentRequest(question="What is the stock position?", sku_id="SKU-999", intent="stock_discrepancy"),
        state=state,
        store=AgentSessionStore(":memory:"),
    ).to_dict()

    inventory = next(step for step in result["steps"] if step["tool"] == "inventory_position")
    assert inventory["status"] == "error"
    assert inventory["code"] == "not_found"
    assert "not_found" in result["failure_labels"]
    assert result["failure_taxonomy"]["not_found"] == "tool_call_error"
    assert result["status"] == "failed"


def test_context_persists_across_turns(state, demo_request):
    demo_request.conversation_id = "conv-turns"
    store = AgentSessionStore(":memory:")

    first = run_review(demo_request, store=store)
    second = run_review(
        AgentRequest(
            question="What if the same delay becomes four days instead?",
            delay_days=4,
            conversation_id="conv-turns",
        ),
        store=store,
    )

    assert first.turn == 1
    assert second.turn == 2
    assert second.context["sku_id"] == SKU
    assert second.context["supplier_id"] == SUPPLIER
    assert "inventory_position" in [step["tool"] for step in second.to_dict()["steps"]]
    assert len(store.turns("conv-turns")) == 2


def test_api_review_returns_a_bounded_read_only_run(demo_request):
    response = client.post(
        "/api/v1/agent/review",
        json={
            "question": QUESTION,
            "sku_id": SKU,
            "supplier_id": SUPPLIER,
            "delay_days": 2,
            "intent": "supplier_delay",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["side_effects"] is False
    assert body["conversation_id"].startswith("conv-")
    assert body["budget"]["steps"] <= 10
    assert body["usage"]["estimated_tokens"] <= 12000
    assert body["citations"]
    assert ledger.pending_reviews() == []


def test_api_plan_validation_is_structured(demo_request):
    malformed = client.post("/api/v1/agent/plan/validate", json={"plan": "{bad"})
    assert malformed.status_code == 200
    body = malformed.json()
    assert body["valid"] is False
    assert body["error_code"] == "malformed_json"
    assert body["message"]

    unknown = client.post(
        "/api/v1/agent/plan/validate", json={"plan": {"steps": [{"tool": "drop_tables", "args": {}}]}}
    )
    assert unknown.json()["error_code"] == "unknown_tool"

    good = client.post(
        "/api/v1/agent/plan/validate",
        json={"plan": {"steps": [{"tool": "policy_search", "args": {"query": "delay notice"}}]}},
    )
    body = good.json()
    assert body["valid"] is True
    assert body["plan"]["source"] == "supplied"


def test_api_exposes_tools_and_persisted_sessions(demo_request):
    tools = client.get("/api/v1/agent/tools")
    assert tools.status_code == 200
    assert tools.json()["read_only"] is True
    assert tools.json()["count"] >= 3

    demo_request.conversation_id = "conv-api-session"
    run_review(demo_request, store=agent_store)
    session = client.get("/api/v1/agent/sessions/conv-api-session")
    assert session.status_code == 200
    assert len(session.json()["turns"]) == 1
    assert session.json()["context"]["sku_id"] == SKU

    assert client.get("/api/v1/agent/sessions/conv-missing").status_code == 404


def test_agent_and_tool_spans_are_traced(state, demo_request):
    run_review(demo_request, state=state, store=AgentSessionStore(":memory:"))

    kinds = {span["kind"] for span in trace_store.spans()}
    assert {"agent", "tool"} <= kinds
    summary = trace_store.summary()["totals"]
    assert summary["agent_spans"] >= 1
    assert summary["tool_calls"] >= 1


def test_demo_reset_clears_agent_sessions(demo_request):
    demo_request.conversation_id = "conv-reset"
    run_review(demo_request, store=agent_store)
    assert client.get("/api/v1/agent/sessions/conv-reset").status_code == 200

    response = client.post("/api/v1/demo/reset")

    assert response.status_code == 200
    assert "agent_sessions" in response.json()["cleared"]
    assert client.get("/api/v1/agent/sessions/conv-reset").status_code == 404


def test_intent_scoped_search_cites_only_applicable_documents(state):
    registry = build_registry(state)

    result = registry.call(
        "policy_search",
        {"query": "demand rise next week", "top_k": 3, "event_type": "demand_spike"},
    )

    assert result.status == "ok"
    document_ids = [hit["document_id"] for hit in result.output["hits"]]
    assert "POL-DEM-007" in document_ids
    assert len(document_ids) == len(set(document_ids))
    applicable = set(
        registry.call("policy_metadata", {"event_type": "demand_spike"}).output["applicable"]
    )
    assert set(document_ids) <= applicable


@pytest.mark.parametrize(
    ("intent", "question", "sku_id", "retailer_id", "expected"),
    [
        ("baseline", "What is the standing reorder position for this SKU?", "SKU-003", None, "POL-DEC-008"),
        ("batch_recall", "Recall RCL-001 covers batch BATCH-004. Quarantine it.", "SKU-005", None, "POL-STK-007"),
        ("product_request", "The retailer wants us to list a new pack.", "SKU-006", "RET-005", "POL-MSC-007"),
    ],
)
def test_reviews_complete_with_intent_specific_policy(state, intent, question, sku_id, retailer_id, expected):
    result = run_review(
        AgentRequest(question=question, intent=intent, sku_id=sku_id, retailer_id=retailer_id),
        store=AgentSessionStore(":memory:"),
    ).to_dict()

    assert result["status"] == "ok"
    assert expected in [citation["document_id"] for citation in result["citations"]]


def test_agent_evaluation_measures_completion_and_tool_calls():
    from app.evaluation.agent import run_agent_evaluation

    result = run_agent_evaluation()
    summary = result["summary"]

    assert summary["tasks"] == len(result["rows"]) == 17
    assert summary["completion_rate"] == 1.0
    assert 3 <= summary["avg_tool_calls"] <= 10
    assert summary["latency_ms_p95"] >= summary["latency_ms_p50"] > 0
    assert summary["exceptions"] == 0
    assert all(row["expected_documents"] for row in result["rows"])
