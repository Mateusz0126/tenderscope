import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).parents[1] / ".github/workflows/run-etl-dev.yml"


def python_block(index):
    source = WORKFLOW.read_text(encoding="utf-8")
    return textwrap.dedent(
        source.split("python - <<'PY'\n")[index + 1].split("          PY")[0]
    )


@pytest.mark.parametrize(
    ("since", "until", "pages", "ok"),
    [
        ("2026-01-01", "2026-01-07", "100", True),
        ("2026-01-01", "2026-01-01", "2", True),
        ("2026-01-01", "2026-01-08", "2", False),
        ("2026-01-02", "2026-01-01", "2", False),
        ("20260101", "2026-01-01", "2", False),
        ("2026-01-01", "2026-01-01", "0", False),
        ("2026-01-01", "2026-01-01", "101", False),
        ("2026-01-01", "2026-01-01", "2; echo unsafe", False),
    ],
)
def test_dispatch_validation(since, until, pages, ok):
    result = subprocess.run(
        [sys.executable, "-c", python_block(0)],
        env={**os.environ, "SINCE": since, "UNTIL": until, "MAX_PAGES": pages},
        check=False,
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) == ok, result.stderr


def test_summary_reports_failure_before_execution(tmp_path):
    target = tmp_path / "summary.md"
    steps = {
        "validate": {"outcome": "success"},
        "login": {"outcome": "failure"},
        "execution": {"outcome": "skipped"},
        "wait": {"outcome": "skipped"},
    }
    result = subprocess.run(
        [sys.executable, "-c", python_block(1)],
        env={
            **os.environ,
            "STEPS_JSON": json.dumps(steps),
            "SINCE": "<unsafe>",
            "UNTIL": "2026-01-01",
            "MAX_PAGES": "2",
            "GITHUB_STEP_SUMMARY": str(target),
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    text = target.read_text(encoding="utf-8")
    assert "login" in text and "Not started" in text and "&lt;unsafe&gt;" in text
    assert "<unsafe>" not in text
