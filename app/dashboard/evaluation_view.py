from __future__ import annotations

import time
import urllib.error
from datetime import datetime, timezone
from html import escape

import streamlit as st

from app.dashboard.theme import badge, empty_state, metric_card, page_header, quote_html, section_title


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _milliseconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} ms"


def _elapsed(job: dict) -> str:
    started = job.get("started_at") or job.get("created_at")
    if not started:
        return "0 s"
    begin = datetime.fromisoformat(started)
    end = datetime.fromisoformat(job["completed_at"]) if job.get("completed_at") else datetime.now(timezone.utc)
    return f"{max(0, (end - begin).total_seconds()):.1f} s"


def start_evaluation(kind: str, post) -> None:
    try:
        job = post(f"/api/v1/evaluations/{kind}/run", {})
    except urllib.error.HTTPError as exc:
        st.error(f"Evaluation could not start: API returned {exc.code}: {exc.read().decode('utf-8')}")
        return
    except urllib.error.URLError as exc:
        st.error(f"Cannot reach the evaluation API: {exc.reason}")
        return
    st.session_state.active_evaluation_job = job["job_id"]
    st.session_state.active_evaluation_kind = kind


def render_live_evaluation(job_id: str, get) -> None:
    placeholder = st.empty()
    while True:
        try:
            job = get(f"/api/v1/evaluations/{job_id}")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            st.error(f"Lost contact with the evaluation API: {exc}")
            return
        total = job.get("total") or 0
        current = job.get("current") or 0
        activities = job.get("activities") or []
        latest = activities[-1] if activities else {}
        with placeholder.container():
            with st.container(border=True):
                section_title(
                    f"Running {job['kind']} evaluation",
                    "Each item is executed and scored; progress below comes from the running job.",
                )
                st.progress(current / total if total else 0.0, text=f"{current}/{total or '—'} items completed")
                st.write(f"**{latest.get('title', 'Preparing evaluation')}**")
                if latest.get("detail"):
                    st.caption(latest["detail"])
                columns = st.columns(3)
                columns[0].metric("Completed", f"{current}/{total or '—'}")
                columns[1].metric("Elapsed", _elapsed(job))
                columns[2].metric("Recorded steps", len(activities))
                if activities:
                    st.dataframe(
                        [
                            {
                                "Step": activity["step"].replace("_", " "),
                                "Activity": activity["title"],
                                "Detail": activity.get("detail", ""),
                                "Outcome": activity.get("outcome", "running"),
                            }
                            for activity in reversed(activities[-10:])
                        ],
                        width="stretch",
                        hide_index=True,
                    )
        if job["status"] == "completed":
            st.session_state[f"evaluation_{job['kind']}"] = job
            st.session_state.pop("active_evaluation_job", None)
            st.session_state.pop("active_evaluation_kind", None)
            st.rerun()
        if job["status"] == "failed":
            st.error(f"Evaluation failed: {job.get('error') or 'unknown error'}")
            st.session_state.pop("active_evaluation_job", None)
            st.session_state.pop("active_evaluation_kind", None)
            return
        time.sleep(0.35)


def _render_rag_results(job: dict) -> None:
    result = job["result"]
    summary = result["summary"]
    rows = result["rows"]
    st.caption(f"Completed {job['completed_at']} · job {job['job_id']} · {summary['queries']} frozen golden queries")
    columns = st.columns(5)
    values = [
        ("Primary @1", _percent(summary["primary_at_1"]), "Expected document ranked first", "accent"),
        ("Recall @3", _percent(summary["recall_at_3"]), "Expected or accepted document in top 3", "success"),
        ("MRR", f"{summary['mrr']:.3f}", "Rewards finding the expected document earlier", "accent"),
        ("Latency p50", _milliseconds(summary["latency_ms_p50"]), "Median local retrieval time", "accent"),
        ("Latency p95", _milliseconds(summary["latency_ms_p95"]), "95th-percentile retrieval time", "accent"),
    ]
    for column, value in zip(columns, values):
        with column:
            metric_card(*value)
    st.write("")
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            section_title("BM25 versus simple term counting", "Both rankers receive the same 40 questions.")
            st.dataframe(
                [
                    {"Metric": "Primary @1", "BM25": _percent(summary["primary_at_1"]), "Term frequency": _percent(summary["baseline_primary_at_1"])},
                    {"Metric": "Recall @3", "BM25": _percent(summary["recall_at_3"]), "Term frequency": _percent(summary["baseline_recall_at_3"])},
                    {"Metric": "MRR", "BM25": f"{summary['mrr']:.3f}", "Term frequency": f"{summary['baseline_mrr']:.3f}"},
                ],
                width="stretch",
                hide_index=True,
            )
    with right:
        with st.container(border=True):
            citations = summary["citation_coverage"]
            section_title("Review-card citation coverage", "SCN-003 is processed with deterministic rules for this check.")
            st.write(f"**{citations['with_quote']}/{citations['references']}** references contain a verbatim quote")
            st.write(f"**{citations['with_provenance']}/{citations['references']}** contain document, effective-date and licence provenance")
            st.caption("Documents: " + ", ".join(citations["document_ids"]))
    section_title(
        "Every query and its outcome",
        f"{summary['corpus_documents']} documents · {summary['corpus_sections']} sections · {summary['corpus_bytes'] / 1024:.1f} KiB corpus",
    )
    st.dataframe(
        [
            {
                "Query": row["id"],
                "Expected": row["expected"],
                "Top document": row["ranked"][0] if row["ranked"] else "—",
                "Expected rank": str(row["ranked"].index(row["expected"]) + 1) if row["expected"] in row["ranked"] else "Not in top 5",
                "Recall @3": "Pass" if row["hit_at_3"] else "Miss",
                "Latency": _milliseconds(row["latency_ms"]),
            }
            for row in rows
        ],
        width="stretch",
        hide_index=True,
    )
    selected_id = st.selectbox("Inspect a retrieval query", [row["id"] for row in rows])
    selected = next(row for row in rows if row["id"] == selected_id)
    with st.container(border=True):
        st.write(f"**{selected['query']}**")
        st.caption(f"Expected {selected['expected']} · accepted answers: {', '.join(selected['acceptable'])}")
        for rank, hit in enumerate(selected["hits"], start=1):
            rank_label = f"#{rank} {hit['document_id']}"
            st.markdown(
                f"{badge(rank_label)} **{escape(hit['title'])}**",
                unsafe_allow_html=True,
            )
            st.caption(f"{hit['section_id']} · effective {hit['effective_from']} · {hit['licence']}")
            st.markdown(f"<div class='bb-quote'>{quote_html(hit['quote'])}</div>", unsafe_allow_html=True)


def _extraction_comparison(summary: dict) -> list[dict]:
    rules = summary["variants"]["rules"]
    llm = summary["variants"]["llm"]
    definitions = [
        ("Intent accuracy", "intent_accuracy", _percent, "Correct message category"),
        ("All entity slots", "entity_exact_match", _percent, "Includes correctly preserving unknown fields"),
        ("Stated-fact accuracy", "stated_entity_accuracy", _percent, "Only fields the message actually states"),
        ("Exact record match", "record_exact_match", _percent, "Intent and every labelled entity correct"),
        ("Validation pass rate", "validation_pass_rate", _percent, "Output accepted without rules fallback"),
        ("Verbatim evidence", "verbatim_evidence_rate", _percent, "Retained evidence found exactly in the source"),
        ("Rules fallbacks", "fallback_count", lambda value: str(value), "LLM failures replaced by deterministic rules"),
        ("Latency p50", "latency_ms_p50", _milliseconds, "Median time per message"),
        ("Latency p95", "latency_ms_p95", _milliseconds, "95th-percentile time per message"),
    ]
    return [
        {"Metric": label, "Rules": formatter(rules[key]), "LLM pipeline": formatter(llm[key]), "What it means": meaning}
        for label, key, formatter, meaning in definitions
    ]


def _render_extraction_results(job: dict) -> None:
    result = job["result"]
    summary = result["summary"]
    rows = result["rows"]
    llm = summary["variants"]["llm"]
    st.caption(
        f"Completed {job['completed_at']} · {summary['examples']} held-out evaluation messages · "
        f"{summary['llm_model']} · prompt {summary['prompt_version']}"
    )
    columns = st.columns(5)
    values = [
        ("LLM intent accuracy", _percent(llm["intent_accuracy"]), "Correct message category", "accent"),
        ("Stated-fact accuracy", _percent(llm["stated_entity_accuracy"]), "Fields explicitly present in messages", "accent"),
        ("Exact records", _percent(llm["record_exact_match"]), "Intent and every entity correct", "success"),
        ("Rules fallbacks", str(llm["fallback_count"]), "Failures are visible, not hidden", "warning" if llm["fallback_count"] else "success"),
        ("LLM latency p50", _milliseconds(llm["latency_ms_p50"]), "Includes fallback time when needed", "accent"),
    ]
    for column, value in zip(columns, values):
        with column:
            metric_card(*value)
    st.write("")
    section_title("Rules versus validated LLM pipeline", "The LLM pipeline uses deterministic rules after a model error or validation failure.")
    st.dataframe(_extraction_comparison(summary), width="stretch", hide_index=True)
    section_title("Every held-out message and its outcome", "No held-out record is added to prompts, rules or retrieval queries.")
    st.dataframe(
        [
            {
                "Message": row["message_id"],
                "Expected intent": row["expected_intent"],
                "Rules intent": row["results"]["rules"]["predicted_intent"],
                "LLM intent": row["results"]["llm"]["predicted_intent"],
                "LLM entity slots": f"{row['results']['llm']['entity_correct']}/{row['results']['llm']['entity_total']}",
                "Fallback": "Yes" if row["results"]["llm"]["fallback"] else "No",
                "Exact record": "Pass" if row["results"]["llm"]["record_exact"] else "Miss",
            }
            for row in rows
        ],
        width="stretch",
        hide_index=True,
    )
    selected_id = st.selectbox("Inspect an extraction message", [row["message_id"] for row in rows])
    selected = next(row for row in rows if row["message_id"] == selected_id)
    variant = st.radio("Output to inspect", ["llm", "rules"], format_func=lambda value: "LLM pipeline" if value == "llm" else "Rules", horizontal=True)
    outcome = selected["results"][variant]
    with st.container(border=True):
        st.write(f"**{selected['text']}**")
        st.caption(f"Expected intent: {selected['expected_intent']} · predicted: {outcome['predicted_intent']} · {outcome['latency_ms']:.1f} ms")
        if outcome["fallback"]:
            st.warning("The model output failed or was rejected; deterministic rules produced the final pipeline output shown below.")
        st.dataframe(
            [
                {
                    "Entity": field,
                    "Expected": expected if expected is not None else "unknown",
                    "Predicted": outcome["predicted_entities"][field] or "unknown",
                    "Result": "Match" if outcome["entity_matches"][field] else "Mismatch",
                }
                for field, expected in selected["expected_entities"].items()
            ],
            width="stretch",
            hide_index=True,
        )
        st.dataframe(
            outcome["facts"],
            width="stretch",
            hide_index=True,
            column_config={"evidence_span": "Verbatim evidence"},
        )
        if outcome["validation_violations"]:
            st.warning("Validation: " + "; ".join(outcome["validation_violations"]))
        if outcome["error"]:
            st.error(outcome["error"])
        with st.expander("Label evidence and uncertainty"):
            st.write(selected["label_evidence_spans"])
            st.write(selected["uncertainty"])


def _render_metric_guide() -> None:
    section_title("How to read the evaluation", "Metrics measure different claims; one high percentage does not prove the whole pipeline.")
    st.markdown(
        """
        - **Primary@1:** the canonical expected document is the first retrieval result.
        - **Recall@3:** the expected document, or a labelled acceptable alternative, appears in the first three results.
        - **MRR:** gives more credit when the expected document appears earlier.
        - **Intent accuracy:** whether the extracted primary intent matches the frozen label.
        - **All entity slots:** includes absent fields, so preserving an explicit unknown counts as correct.
        - **Stated-fact accuracy:** evaluates only facts actually present in the message, preventing null-heavy labels from inflating the score.
        - **Exact record match:** requires both the intent and every labelled entity to match.
        - **Validation pass rate:** shows how often model output passes deterministic schema, evidence and catalogue checks.
        - **Rules fallback:** counts model failures replaced by rules; these runs remain visible in the results.
        """
    )
    st.info("The 12 extraction messages are held out from prompt design, rules and RAG queries. Results are measured on that held-out evaluation set.")


def render_evaluation(inference: dict | None, get, post, go_to=None) -> None:
    page_header(
        "Evidence and model quality",
        "Evaluation",
        "Run the frozen RAG and held-out extraction evaluations, watch each check execute, and inspect the evidence behind every result.",
        "Read-only evaluation · no operational decisions or state mutations",
    )
    if go_to is not None:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            left.write(
                "**Track B evidence workspace:** the 80-case gold set, retrieval upgrades, prompting comparison, "
                "bounded agent runtime and safety controls."
            )
            with right:
                if st.button("Open Track B evidence", width="stretch"):
                    go_to("Track B evidence")
    try:
        latest = get("/api/v1/evaluations/latest")
    except (urllib.error.URLError, TimeoutError, ValueError):
        latest = None
    if latest is not None:
        for kind in ("rag", "extraction"):
            job = latest.get(kind)
            st.session_state[f"evaluation_{kind}"] = job if job and job.get("result") is not None else None
    active_job = st.session_state.get("active_evaluation_job")
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            section_title("RAG retrieval", "40 golden questions · BM25 versus term frequency · citation coverage")
            st.write("Checks whether the approved corpus retrieves the right policy and whether review-card quotes are inspectable.")
            st.caption("Local retrieval only. SCN-003 citation coverage explicitly uses rules extraction.")
            st.button(
                "Run RAG evaluation",
                key="run-rag-evaluation",
                type="primary",
                disabled=bool(active_job),
                on_click=start_evaluation,
                args=("rag", post),
                width="stretch",
            )
    with right:
        with st.container(border=True):
            section_title("LLM extraction", "12 held-out messages · rules versus validated LLM pipeline")
            st.write("Compares intent and entity extraction, exact evidence, validation failures, fallbacks and response time.")
            if inference and inference.get("llm_enabled"):
                st.caption(f"Configured model: {inference['model']} · held-out evaluation messages only")
            else:
                st.caption("Enable the configured LLM to run the comparison. RAG evaluation remains available.")
            st.button(
                "Run LLM evaluation",
                key="run-llm-evaluation",
                type="primary",
                disabled=bool(active_job) or not (inference and inference.get("llm_enabled")),
                on_click=start_evaluation,
                args=("extraction", post),
                width="stretch",
            )
    if active_job:
        render_live_evaluation(active_job, get)
    rag_tab, extraction_tab, guide_tab = st.tabs(["RAG results", "Extraction results", "Metric guide"])
    with rag_tab:
        job = st.session_state.get("evaluation_rag")
        if job:
            _render_rag_results(job)
        else:
            empty_state("No RAG result yet", "Run the evaluation to see live progress and inspect all 40 queries.")
    with extraction_tab:
        job = st.session_state.get("evaluation_extraction")
        if job:
            _render_extraction_results(job)
        else:
            empty_state("No extraction result yet", "Enable the LLM and run the evaluation to compare all 12 held-out messages.")
    with guide_tab:
        _render_metric_guide()
