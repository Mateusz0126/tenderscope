import json

import httpx

from tenderscope.ingestion.ted_pages import fetch_pages


def test_pagination_uses_token_and_stops():
    received_tokens = []

    def mock_api(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)

        assert payload["paginationMode"] == "ITERATION"
        received_tokens.append(payload.get("iterationNextToken"))

        if len(received_tokens) == 1:
            return httpx.Response(
                200,
                json={
                    "notices": [
                        {"publication-number": "001-2026"},
                        {"publication-number": "002-2026"},
                    ],
                    "iterationNextToken": "token-abc",
                    "totalNoticeCount": 3,
                    "timedOut": False,
                },
            )

        if len(received_tokens) == 2:
            return httpx.Response(
                200,
                json={
                    "notices": [
                        {"publication-number": "003-2026"},
                    ],
                    "iterationNextToken": None,
                    "totalNoticeCount": 3,
                    "timedOut": False,
                },
            )

        raise AssertionError("Unexpected additional API request")

    transport = httpx.MockTransport(mock_api)

    with httpx.Client(transport=transport) as client:
        pages = list(
            fetch_pages(
                client,
                query="buyer-country=POL",
                max_pages=5,
            )
        )

    assert len(pages) == 2
    assert [page[2] for page in pages] == [2, 1]
    assert received_tokens == [None, "token-abc"]


def test_weekly_iteration_uses_unique_sort_and_preserves_completeness(tmp_path):
    """Replay the 120-result backfill boundary: date sort returned only 97."""
    from datetime import date

    import pytest

    from tenderscope.ingestion.ted_api import build_query
    from tenderscope.ingestion.ted_pages import run_download

    query = build_query(date(2026, 11, 5), date(2026, 11, 11))

    def mock_api(request):
        payload = json.loads(request.content)
        page = int(payload.get("iterationNextToken", "0"))
        unique_sort = payload["query"].endswith("SORT BY publication-number DESC")
        sizes = [50, 50, 20, 0] if unique_sort else [50, 47, 0]
        offset = sum(sizes[:page])
        return httpx.Response(
            200,
            json={
                "notices": [
                    {"publication-number": str(i)}
                    for i in range(offset, offset + sizes[page])
                ],
                "totalNoticeCount": 120,
                "iterationNextToken": str(page + 1),
                "timedOut": False,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(mock_api)) as client:
        run_download(client, tmp_path / "complete", query=query, max_pages=10)
        legacy = query.replace(
            "SORT BY publication-number DESC", "SORT BY publication-date DESC"
        )
        with pytest.raises(RuntimeError, match="received 97, expected 120"):
            run_download(client, tmp_path / "incomplete", query=legacy, max_pages=10)
    complete = json.loads((tmp_path / "complete/manifest.json").read_text())
    assert complete["status"] == "completed"
    assert sum(p["record_count"] for p in complete["pages"]) == 120
    incomplete = json.loads((tmp_path / "incomplete/manifest.json").read_text())
    assert incomplete["status"] == "partial"
