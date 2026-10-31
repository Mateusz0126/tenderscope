
import json

import httpx
import polars as pl

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

    with httpx.Client(
        transport=httpx.MockTransport(mock_ted)
    ) as client:
        result = run_pipeline(
            client,
            run_dir,
            query="buyer-country=POL",
            max_pages=5,
        )

    assert received_tokens == [None, "token-2"]
    assert result["bronze_records"] == 2
    assert result["silver_metrics"]["notices"] == 2
    assert result["quality_metrics"]["checks_passed"] == 8

    manifest = json.loads(
        (run_dir / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

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
