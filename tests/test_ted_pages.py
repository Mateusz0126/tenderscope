
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
