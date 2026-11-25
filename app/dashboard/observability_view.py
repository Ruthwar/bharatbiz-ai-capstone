from __future__ import annotations

import urllib.error
from datetime import datetime

import streamlit as st

from app.dashboard.theme import badge, empty_state, metric_card, page_header, section_title


def _milliseconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} ms"


def _count(value: int | None) -> str:
    return "—" if value is None else f"{value:,}"


def _time(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%d %b %H:%M:%S")
    except ValueError:
        return value


def _session_label(session: str) -> str:
    prefix, _, rest = session.partition(":")
    if prefix == "scenario":
        return f"Scenario {rest}"
    if prefix == "inbound":
        return f"Inbound {rest}"
    if prefix == "message":
        return f"Message {rest}"
    if prefix == "evaluation":
        return f"Evaluation · {rest}"
    return session


def _detail_text(span: dict) -> str:
    detail = span.get("detail") or {}
    if span["kind"] == "retrieval":
        documents = ", ".join(detail.get("documents") or []) or "no documents"
        return f"“{detail.get('query') or '—'}” → {documents}"
    if span["kind"] == "fallback":
        return f"Rules used after {detail.get('reason') or 'a model failure'}."
    parts = []
    if detail.get("selection"):
        parts.append(f"Selected {detail['selection']}")
    if detail.get("abstain_reason"):
        parts.append(f"Abstained: {detail['abstain_reason']}")
    if detail.get("citations"):
        parts.append("Cited " + ", ".join(detail["citations"]))
    if "intents" in detail:
        parts.append(f"{detail.get('intents', 0)} intents, {detail.get('facts', 0)} facts")
    return "; ".join(parts) or "—"


def _span_rows(spans: list[dict]) -> list[dict]:
    return [
        {
            "Step": span["step"],
            "Kind": span["kind"],
            "Status": span["status"],
            "Model": span.get("model") or "—",
            "Started": _time(span["started_at"]),
            "Latency": _milliseconds(span.get("latency_ms")),
            "Tokens": _count(
                (span.get("prompt_tokens") or 0) + (span.get("completion_tokens") or 0)
            ),
            "Detail": _detail_text(span),
        }
        for span in spans
    ]


def _render_activity(data: dict) -> None:
    section_title(
        "Where time and tokens went",
        "Only model generations carry tokens; retrieval calls are local BM25 lookups.",
    )
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            section_title("By step", "One row per instrumented call site.")
            st.dataframe(
                [
                    {
                        "Step": row["step"],
                        "Kind": row["kind"],
                        "Spans": row["spans"],
                        "Errors": row["errors"],
                        "Tokens": _count(row["tokens"]),
                        "Avg latency": _milliseconds(row["avg_latency_ms"]),
                    }
                    for row in data["by_step"]
                ],
                width="stretch",
                hide_index=True,
            )
    with right:
        with st.container(border=True):
            section_title("By model", "Provider and model as configured, without credentials.")
            st.dataframe(
                [
                    {
                        "Provider": row["provider"],
                        "Model": row["model"],
                        "Calls": row["generations"],
                        "Tokens": _count(row["tokens"]),
                        "Errors": row["errors"],
                        "Avg latency": _milliseconds(row["avg_latency_ms"]),
                    }
                    for row in data["models"]
                ],
                width="stretch",
                hide_index=True,
            )

    section_title(
        "Sessions",
        "A session groups work: a scenario run, an inbound conversation or an evaluation job.",
    )
    st.dataframe(
        [
            {
                "Session": _session_label(row["session"]),
                "Source": row["source"],
                "Spans": row["spans"],
                "Model calls": row["generations"],
                "Tokens": _count(row["tokens"]),
                "Errors": row["errors"],
                "First activity": _time(row["first_at"]),
                "Last activity": _time(row["last_at"]),
            }
            for row in data["sessions"]
        ],
        width="stretch",
        hide_index=True,
    )

    section_title("Recent spans", "Newest first. Detail is written by the call site, not the model.")
    recent = data["recent"]
    if not recent:
        empty_state(
            "No spans recorded yet",
            "Run a scenario, send an inbound message or start the LLM evaluation; every model and retrieval call appears here.",
        )
        return
    sessions = sorted({span["session"] for span in recent})
    choice = st.selectbox(
        "Filter by session",
        ["All sessions"] + sessions,
        format_func=lambda value: value if value == "All sessions" else _session_label(value),
    )
    filtered = recent if choice == "All sessions" else [span for span in recent if span["session"] == choice]
    st.dataframe(_span_rows(filtered), width="stretch", hide_index=True)


def _render_runs(data: dict, get) -> None:
    runs = data["runs"]
    if not runs:
        empty_state(
            "No runs recorded yet",
            "A run appears when a message, scenario or evaluation produces at least one model or retrieval call.",
        )
        return
    section_title(
        "Runs",
        "Each run is one trace. Select a run to see every span that belonged to it.",
    )
    labels = {
        run["trace_id"]: (
            f"{_session_label(run['session'])} · {_time(run['started_at'])} · "
            f"{run['spans']} span{'s' if run['spans'] != 1 else ''}"
        )
        for run in runs
    }
    st.dataframe(
        [
            {
                "Run": _session_label(run["session"]),
                "Source": run["source"],
                "Started": _time(run["started_at"]),
                "Spans": run["spans"],
                "Model calls": run["generations"],
                "Retrieval calls": run["retrieval_calls"],
                "Tokens": _count(run["tokens"]),
                "Errors": run["errors"],
                "Steps": " → ".join(run["steps"]),
            }
            for run in runs
        ],
        width="stretch",
        hide_index=True,
    )
    selected = st.selectbox("Inspect a run", [run["trace_id"] for run in runs], format_func=labels.get)
    try:
        trace = get(f"/api/v1/observability/traces/{selected}")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        st.error(f"Could not load the selected run: {exc}")
        return
    columns = st.columns(3)
    with columns[0]:
        metric_card("Spans", str(len(trace["spans"])), trace["trace_id"])
    with columns[1]:
        tokens = sum(
            (span.get("prompt_tokens") or 0) + (span.get("completion_tokens") or 0)
            for span in trace["spans"]
        )
        metric_card("Tokens", _count(tokens), "Reported by the gateway when available")
    with columns[2]:
        errors = sum(1 for span in trace["spans"] if span["status"] == "error")
        metric_card("Errors", str(errors), "Failed model calls and unparseable output", "warning" if errors else "success")
    st.markdown(
        f"{badge(_session_label(trace['session']), 'neutral')} "
        f"{badge(trace['source'], 'neutral')} "
        + (f"{badge(trace['scenario_id'], 'success')}" if trace.get("scenario_id") else ""),
        unsafe_allow_html=True,
    )
    st.dataframe(_span_rows(trace["spans"]), width="stretch", hide_index=True)
    with st.expander("Inspect raw span records"):
        st.caption("These are the exact records stored locally. Prompt bodies and full message text are not stored.")
        st.json(trace["spans"])


def _render_method() -> None:
    section_title(
        "What this records and what it does not",
        "A local trace store shaped like Langfuse; it is not a Langfuse deployment.",
    )
    st.markdown(
        """
        - **One trace per unit of work.** A scenario run, inbound message or evaluation job opens a
          trace; each model call, retrieval call and rules fallback inside it becomes one span.
        - **Tokens come from the gateway.** The `usage` field returned by the model server is stored
          when present; a blank count means the gateway did not report it.
        - **Latency is per call.** It measures the HTTP request or BM25 search, not the end-to-end
          scenario, and it includes time spent waiting on the model server.
        - **No prompts or message bodies are stored.** Spans keep the message id, event type, query
          text, selected option id, citations and small counts.
        - **Deterministic runs can record nothing.** Rules extraction with no persisted review makes
          no model or retrieval call, so there is no span to record. That is the intended difference
          between the modes, not a tracing failure.
        - **Cost is not priced by default.** Set `BHARATBIZ_TRACE_COST_PER_1K_TOKENS` to show an
          illustrative estimate from reported tokens; it is not a billing figure.
        - **Export is opt-in.** Set `BHARATBIZ_TRACE_EXPORT=langfuse` plus `LANGFUSE_HOST`,
          `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` to also send spans to the documented
          Langfuse ingestion endpoint. This hook has not been verified against a live Langfuse
          instance in this project.
        - **Reset clears it.** The sidebar demo reset deletes recorded spans along with the other
          demo state; the evaluation results in the Evaluation tab are separate.
        """
    )
    st.info(
        "Observability is evidence, not a decision. The deterministic outcome, human review and "
        "policy citations shown elsewhere remain the authoritative record of what happened."
    )


def render_observability(get) -> None:
    page_header(
        "Model and retrieval telemetry",
        "LLM observability",
        "Every extraction, policy-decision and retrieval call is recorded as a local span: latency, "
        "reported tokens, status and the ids the application used. Nothing leaves this machine unless "
        "an exporter is configured.",
        "Read-only telemetry · advisory, not an operational decision",
    )
    try:
        data = get("/api/v1/observability")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        st.error(f"Cannot load observability data from the API: {exc}")
        return

    totals = data["totals"]
    tokens = data["tokens"]
    latency = data["latency_ms"]
    export = data["export"]
    columns = st.columns(5)
    values = [
        ("Model calls", _count(totals["generations"]), f"{totals['retrieval_calls']} retrieval calls in the same store", "accent"),
        ("Reported tokens", _count(tokens["total"]), f"{_count(tokens['prompt'])} prompt · {_count(tokens['completion'])} completion", "accent"),
        ("Latency p50", _milliseconds(latency["p50"]), "Per model call, not end to end", "accent"),
        ("Latency p95", _milliseconds(latency["p95"]), f"Max {_milliseconds(latency['max'])}", "accent"),
        (
            "Errors",
            str(totals["errors"]),
            f"{totals['fallbacks']} rules fallback{'s' if totals['fallbacks'] != 1 else ''} · {totals['exported']} exported",
            "warning" if totals["errors"] else "success",
        ),
    ]
    for column, value in zip(columns, values):
        with column:
            metric_card(*value)
    st.write("")

    if export["enabled"]:
        st.caption(f"Langfuse export is on for {export['host']}. {export['reason']} The ingestion hook is not verified live here.")
    else:
        st.caption(f"Langfuse export is off. {export['reason']} Spans stay in {data['database']}.")
    cost = data["cost"]
    if cost["estimated"] is not None:
        st.caption(f"Token estimate at the configured rate: {cost['estimated']:.4f}. This is illustrative, not a bill.")
    else:
        st.caption("Cost is not estimated because no token rate is configured; tokens may be blank when the gateway omits usage.")

    if totals["spans"] == 0:
        empty_state(
            "No model or retrieval activity yet",
            "Run a scenario in Scenario lab, send a message in Inbox, or start the LLM evaluation. "
            "Spans are recorded as those calls happen.",
        )
        return

    activity_tab, runs_tab, method_tab = st.tabs(["Activity", "Runs", "Method"])
    with activity_tab:
        _render_activity(data)
    with runs_tab:
        _render_runs(data, get)
    with method_tab:
        _render_method()
