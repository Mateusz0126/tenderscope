
import json

import httpx
import pytest

from tenderscope.ingestion.ted_pages import run_download


def test_resume_after_failure(tmp_path):
    requests = []
    failed_once = False

    def mock_api(request):
        nonlocal failed_once

        payload = json.loads(request.content)
        token = payload.get("iterationNextToken")
        requests.append(token)

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
            if not failed_once:
                failed_once = True
                raise RuntimeError("Simulated worker crash")

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

    with httpx.Client(
        transport=httpx.MockTransport(mock_api)
    ) as client:

        # First execution: fails on page 2
        with pytest.raises(
            RuntimeError,
            match="Simulated worker crash",
        ):
            run_download(
                client,
                run_dir,
                query="buyer-country=POL",
                max_pages=2,
            )

        first_page = (
            run_dir / "page_001.json"
        ).read_bytes()

        checkpoint = json.loads(
            (run_dir / "manifest.json").read_text(
                encoding="utf-8"
            )
        )

        assert checkpoint["status"] == "partial"
        assert len(checkpoint["pages"]) == 1
        assert checkpoint["next_token"] == "token-2"

        # Second execution: resumes from page 2
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

    assert requests == [None, "token-2", "token-2"]
    assert len(manifest["pages"]) == 2
    assert manifest["status"] == "completed"

    assert (run_dir / "page_001.json").read_bytes() == first_page
    assert (run_dir / "page_002.json").exists()
