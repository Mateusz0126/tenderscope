import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).parents[1] / ".github/workflows/run-etl-dev.yml"


def python_block(step):
    source = WORKFLOW.read_text(encoding="utf-8")
    section = source.split(f"      - name: {step}\n", 1)[1].split("      - name:", 1)[0]
    return textwrap.dedent(
        section.split("python - <<'PY'\n", 1)[1].split("          PY")[0]
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
        [sys.executable, "-c", python_block("Validate date window")],
        env={
            **os.environ,
            "SINCE": since,
            "UNTIL": until,
            "MAX_PAGES": pages,
            "MODE": "incremental",
        },
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
        [sys.executable, "-c", python_block("Summarize execution")],
        env={
            **os.environ,
            "STEPS_JSON": json.dumps(steps),
            "SINCE": "<unsafe>",
            "UNTIL": "2026-01-01",
            "MAX_PAGES": "2",
            "MODE": "incremental",
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


@pytest.mark.parametrize("mode", ["incremental", "backfill"])
def test_execution_template_is_bounded_and_preserves_runtime_config(tmp_path, mode):
    original = {
        "containers": [
            {
                "name": "etl",
                "image": "example.azurecr.io/etl@sha256:" + "a" * 64,
                "command": ["/app/.venv/bin/python", "-m", "tenderscope.pipeline"],
                "args": ["--allow-partial"],
                "env": [{"name": "AZURE_CLIENT_ID", "value": "test-id"}],
                "resources": {"cpu": 0.5, "memory": "1Gi"},
            }
        ],
    }
    (tmp_path / "current-template.json").write_text(json.dumps(original))
    output = tmp_path / "outputs.txt"
    result = subprocess.run(
        [sys.executable, "-c", python_block("Prepare one-time execution template")],
        cwd=tmp_path,
        env={
            **os.environ,
            "MODE": mode,
            "SINCE": "2026-11-05",
            "UNTIL": "2026-11-11",
            "MAX_PAGES": "10",
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    template = json.loads((tmp_path / "execution-template.yaml").read_text())
    container = template["containers"][0]
    args = container.pop("args")
    expected_container = original["containers"][0]
    expected_container.pop("args")
    assert container == expected_container
    assert "--allow-partial" not in args
    options = dict(zip(args[::2], args[1::2], strict=True))
    assert options == {
        "--since": "2026-11-05",
        "--until": "2026-11-11",
        "--max-pages": "10",
        "--state-policy": "enforce" if mode == "incremental" else "off",
        "--storage-prefix": "runs"
        if mode == "incremental"
        else "backfills/2026-11-05_2026-11-11",
    }


def test_unknown_mode_rejected_before_azure():
    result = subprocess.run(
        [sys.executable, "-c", python_block("Validate date window")],
        env={
            **os.environ,
            "MODE": "anything",
            "SINCE": "2026-01-01",
            "UNTIL": "2026-01-01",
            "MAX_PAGES": "2",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Mode must be" in result.stderr
