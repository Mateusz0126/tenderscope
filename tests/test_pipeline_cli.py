from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import tenderscope.pipeline as pipeline_module
from tenderscope.orchestration.state import PipelineState, StateSnapshot
from tenderscope.pipeline import build_execution_plan, create_parser

NOW = datetime(2026, 11, 14, 22, 0, tzinfo=UTC)


def make_plan(*arguments: str):
    parser = create_parser()
    args = parser.parse_args(list(arguments))
    return build_execution_plan(args, parser, now=NOW)


def test_explicit_window_builds_deterministic_run_plan():
    plan = make_plan(
        "--since",
        "2026-11-12",
        "--until",
        "2026-11-13",
        "--max-pages",
        "4",
    )

    assert plan.run_dir == Path("data/raw/ted_20261114T220000000000Z")
    assert "publication-date>=20261112" in plan.query
    assert "publication-date<=20261113" in plan.query
    assert plan.max_pages == 4
    assert plan.publisher is None
    assert plan.state_committer is None


def test_resume_plan_has_no_new_query():
    plan = make_plan("--resume", "data/raw/ted_existing")

    assert plan.run_dir == Path("data/raw/ted_existing")
    assert plan.query is None


def test_durable_plan_uses_snapshot_and_next_date(monkeypatch):
    state = PipelineState(
        stream="ted-poland-it",
        last_completed_date=date(2026, 11, 11),
        last_run_id="ted_previous",
        updated_at_utc=datetime(2026, 11, 13, 20, 0, tzinfo=UTC),
    )

    monkeypatch.setattr(
        pipeline_module,
        "read_pipeline_state",
        lambda *args, **kwargs: StateSnapshot(state=state, etag='"etag"'),
    )

    plan = make_plan(
        "--storage-account",
        "sttenderscope123123",
        "--state-policy",
        "enforce",
        "--since",
        "2026-11-12",
        "--until",
        "2026-11-12",
    )

    assert "publication-date>=20261112" in plan.query
    assert "publication-date<=20261112" in plan.query
    assert plan.publisher is not None
    assert plan.state_committer is not None


def test_durable_plan_rejects_partial_ingestion(capsys):
    parser = create_parser()
    args = parser.parse_args(
        [
            "--storage-account",
            "sttenderscope123123",
            "--state-policy",
            "enforce",
            "--allow-partial",
        ]
    )

    with pytest.raises(SystemExit, match="2"):
        build_execution_plan(args, parser, now=NOW)

    assert "cannot advance a partial ingestion" in capsys.readouterr().err
