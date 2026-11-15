import json

import httpx
import polars as pl
import pytest

import tenderscope.pipeline as pipeline_module
from tenderscope.pipeline import run_pipeline


def make_notice(notice_id: str, cpv: str) -> dict:
    return {
        "publication-number": notice_id,
        "publication-date": "2026-10-30+01:00",
        "notice-title": {
            "pol": f"Przetarg {notice_id}",
            "eng": f"Tender {notice_id}",
        },
        "buyer-name": {
            "pol": ["Test Company"],
        },
        "classification-cpv": [cpv, cpv],
        "notice-type": "can-standard",
        "links": {
            "xml": {
                "MUL": "https://example.com/test.xml",
            }
        },
    }


def test_pipeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    run_dir = tmp_path / "data/raw/ted_test"
    received_tokens = []
    published = {}

    def publish(bronze_dir, silver_dir, gold_dir):
        published["bronze_dir"] = bronze_dir
        published["silver_dir"] = silver_dir
        published["gold_dir"] = gold_dir
        return {"success_marker": "runs/ted_test/_SUCCESS.json"}

    def mock_ted(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        token = payload.get("iterationNextToken")

        received_tokens.append(token)

        if token is None:
            return httpx.Response(
                200,
                json={
                    "notices": [
                        make_notice("001-2026", "72267000"),
                    ],
                    "iterationNextToken": "token-2",
                    "totalNoticeCount": 2,
                    "timedOut": False,
                },
            )

        if token == "token-2":
            return httpx.Response(
                200,
                json={
                    "notices": [
                        make_notice("002-2026", "72262000"),
                    ],
                    "iterationNextToken": None,
                    "totalNoticeCount": 2,
                    "timedOut": False,
                },
            )

        raise AssertionError("Unexpected API request")

    with httpx.Client(transport=httpx.MockTransport(mock_ted)) as client:
        result = run_pipeline(
            client,
            run_dir,
            query="buyer-country=POL",
            max_pages=5,
            publisher=publish,
        )

    assert received_tokens == [None, "token-2"]
    assert result["bronze_records"] == 2
    assert result["silver_metrics"]["notices"] == 2
    assert result["quality_metrics"]["checks_passed"] == 8
    assert result["gold_metrics"] == {
        "notices": 2,
        "unique_buyers": 1,
        "unique_cpv_codes": 2,
        "notice_types": 1,
        "files": 6,
    }
    assert result["storage_metrics"] == {
        "success_marker": "runs/ted_test/_SUCCESS.json"
    }
    assert published["bronze_dir"] == run_dir
    assert published["silver_dir"].resolve() == (tmp_path / "data/silver/ted_test")
    assert published["gold_dir"].resolve() == (tmp_path / "data/gold/ted_test")

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["status"] == "completed"
    assert len(manifest["pages"]) == 2

    silver_dir = tmp_path / "data/silver/ted_test"

    notices = pl.read_parquet(silver_dir / "notice.parquet")
    cpvs = pl.read_parquet(silver_dir / "notice_cpv.parquet")
    buyers = pl.read_parquet(silver_dir / "notice_buyer.parquet")

    assert notices.height == 2
    assert cpvs.height == 2
    assert buyers.height == 2
    assert set(notices["notice_id"].to_list()) == {
        "001-2026",
        "002-2026",
    }


def test_pipeline_does_not_publish_when_quality_fails(
    tmp_path,
    monkeypatch,
):
    run_dir = tmp_path / "data/raw/ted_test"
    publish_calls = []

    monkeypatch.setattr(
        pipeline_module,
        "run_download",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        pipeline_module,
        "load_bronze_run",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        pipeline_module,
        "write_silver",
        lambda *args, **kwargs: {},
    )

    def fail_quality(*args, **kwargs):
        raise RuntimeError("quality failed")

    monkeypatch.setattr(
        pipeline_module,
        "validate_silver",
        fail_quality,
    )

    def publish(*args):
        publish_calls.append(args)
        return {}

    with pytest.raises(RuntimeError, match="quality failed"):
        run_pipeline(
            object(),
            run_dir,
            query="buyer-country=POL",
            max_pages=1,
            publisher=publish,
        )

    assert publish_calls == []


def test_pipeline_commits_state_only_after_publication(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "data/raw/ted_empty"
    events = []

    def mock_ted(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "notices": [],
                "iterationNextToken": None,
                "totalNoticeCount": 0,
                "timedOut": False,
            },
        )

    def publish(*args):
        events.append("published")
        return {"success_marker": "runs/ted_empty/_SUCCESS.json"}

    def commit(run_id):
        events.append("state_committed")
        assert run_id == "ted_empty"
        return {"last_completed_date": "2026-11-11"}

    with httpx.Client(transport=httpx.MockTransport(mock_ted)) as client:
        result = run_pipeline(
            client,
            run_dir,
            query="publication-date>=20261111",
            max_pages=1,
            publisher=publish,
            state_committer=commit,
        )

    assert events == ["published", "state_committed"]
    assert result["state_metrics"] == {"last_completed_date": "2026-11-11"}


def test_pipeline_rejects_state_without_publication(tmp_path):
    with pytest.raises(ValueError, match="requires successful ADLS"):
        run_pipeline(
            object(),
            tmp_path / "data/raw/ted_test",
            query="buyer-country=POL",
            max_pages=1,
            state_committer=lambda run_id: {},
        )


def test_pipeline_rejects_partial_state_commit(tmp_path):
    with pytest.raises(ValueError, match="cannot advance a partial"):
        run_pipeline(
            object(),
            tmp_path / "data/raw/ted_test",
            query="buyer-country=POL",
            max_pages=1,
            allow_partial=True,
            publisher=lambda *args: {},
            state_committer=lambda run_id: {},
        )


def test_pipeline_accepts_completed_empty_date_window(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "data/raw/ted_empty"

    def mock_ted(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "notices": [],
                "iterationNextToken": None,
                "totalNoticeCount": 0,
                "timedOut": False,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(mock_ted)) as client:
        result = run_pipeline(
            client,
            run_dir,
            query=("publication-date>=20261101 AND publication-date<=20261101"),
            max_pages=1,
        )

    summary = json.loads((tmp_path / "data/gold/ted_empty/summary.json").read_text())
    assert summary["extraction"]["requested_window"] == {
        "from": "2026-11-01",
        "to": "2026-11-01",
    }
    assert summary["date_range"] == {"from": None, "to": None}
    assert summary["extraction"]["status"] == "completed"
    assert result["bronze_records"] == 0
    assert result["silver_metrics"] == {
        "notices": 0,
        "cpv_relationships": 0,
        "buyer_relationships": 0,
    }
    assert result["quality_metrics"] == {
        "bronze_records": 0,
        "silver_records": 0,
        "checks_passed": 8,
    }
    assert result["gold_metrics"] == {
        "notices": 0,
        "unique_buyers": 0,
        "unique_cpv_codes": 0,
        "notice_types": 0,
        "files": 6,
    }

    silver_dir = tmp_path / "data/silver/ted_empty"

    assert pl.read_parquet(silver_dir / "notice.parquet").schema == {
        "notice_id": pl.String,
        "publication_date": pl.Date,
        "publication_date_raw": pl.String,
        "title_pl": pl.String,
        "title_en": pl.String,
        "notice_type": pl.String,
        "xml_url": pl.String,
    }


@pytest.mark.parametrize("complete", [False, True])
def test_report_preserves_requested_scope_and_completeness(
    tmp_path, monkeypatch, complete
):
    monkeypatch.chdir(tmp_path)

    def respond(request):
        return httpx.Response(
            200,
            json={
                "notices": [make_notice("001-2026", "72000000")],
                "iterationNextToken": None if complete else "more",
                "totalNoticeCount": 1 if complete else 2,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        run_pipeline(
            client,
            tmp_path / "data/raw/ted_scope",
            query="publication-date>=20261029 AND publication-date<=20261031",
            max_pages=1,
            allow_partial=True,
        )
    output = tmp_path / "data/gold/ted_scope"
    summary = json.loads((output / "summary.json").read_text())
    assert summary["extraction"]["status"] == ("completed" if complete else "partial")
    assert summary["extraction"]["requested_window"] == {
        "from": "2026-10-29",
        "to": "2026-10-31",
    }
    assert summary["date_range"] == {"from": "2026-10-30", "to": "2026-10-30"}
    report = (output / "report.html").read_text(encoding="utf-8")
    assert ("PARTIAL SAMPLE" in report) is not complete
    assert "Distinct buyer names" in report
    assert summary["quality_verified"] is True
