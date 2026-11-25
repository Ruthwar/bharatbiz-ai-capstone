"""Dashboard evaluation state follows the API, not a stale browser session."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _sync_script(*, latest, fail):
    import streamlit as st

    from app.dashboard.track_b_view import _latest_jobs

    def get(path):
        if fail:
            raise ValueError("API offline")
        return latest

    _latest_jobs(get)
    st.write("synced")


def _render(*, latest, fail=False):
    app = AppTest.from_function(
        _sync_script,
        kwargs={"latest": latest, "fail": fail},
    )
    return app


def test_completed_remote_job_replaces_stale_state():
    app = _render(
        latest={
            "agent": {"job_id": "eval-new", "status": "completed", "result": {}},
            "track_b": {"job_id": "eval-running", "status": "running", "result": None},
            "prompting": None,
        }
    )
    app.session_state["evaluation_agent"] = {"job_id": "eval-old", "result": {}}
    app.session_state["evaluation_track_b"] = {"job_id": "eval-old", "result": {}}

    app.run()

    assert not app.exception
    assert app.session_state["evaluation_agent"]["job_id"] == "eval-new"
    assert app.session_state["evaluation_track_b"] is None
    assert app.session_state["evaluation_prompting"] is None


def test_unreachable_api_keeps_the_last_result():
    app = _render(latest=None, fail=True)
    app.session_state["evaluation_agent"] = {"job_id": "eval-old", "result": {}}

    app.run()

    assert not app.exception
    assert app.session_state["evaluation_agent"]["job_id"] == "eval-old"
