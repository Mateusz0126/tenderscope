
import json

import httpx

from tenderscope.ingestion.ted_pages import run_download


def test_resume_from_saved_checkpoint(tmp_path):
    received_tokens = []

    def mock_api(request):
        payload = json.loads(request.content)
        token = payload.get("iterationNextToken")
        received_tokens.append(token)

        if token is None:
            return httpx.Response(
                200,
                json={
                    "notices": [
                        {"publication-number": "001-2026"},
                        {"publication-number": "002-2026"},
                    ],
                    "iterationNextToken": "token-2",
                    "totalNoticeCount": 3,
                    "timedOut": False,
                },
            )

        if token == "token-2":
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

        raise AssertionError("Unexpected token")

    run_dir = tmp_path / "test_run"
    transport = httpx.MockTransport(mock_api)

    with httpx.Client(transport=transport) as client:
        # First execution: only page 1
        run_download(
            client,
            run_dir,
            query="buyer-country=POL",
            max_pages=1,
        )

        # Resume: page 2, without repeating page 1
        run_download(
            client,
            run_dir,
            max_pages=2,
        )

        # Completed run should not issue further requests
        run_download(
            client,
            run_dir,
            max_pages=2,
        )

    manifest = json.loads(
        (run_dir / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert received_tokens == [None, "token-2"]
    assert len(manifest["pages"]) == 2
    assert manifest["status"] == "completed"
    assert manifest["next_token"] is None

    assert (run_dir / "page_001.json").exists()
    assert (run_dir / "page_002.json").exists()
