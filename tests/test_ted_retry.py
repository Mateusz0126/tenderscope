
import httpx
import pytest

from tenderscope.ingestion.ted_pages import post_with_retry


def test_retry_after_503():
    attempts = 0
    delays = []

    def mock_api(request):
        nonlocal attempts
        attempts += 1

        if attempts < 3:
            return httpx.Response(503)

        return httpx.Response(200, json={"notices": []})

    with httpx.Client(
        transport=httpx.MockTransport(mock_api)
    ) as client:
        response = post_with_retry(
            client,
            {"query": "test"},
            sleep_fn=delays.append,
        )

    assert response.status_code == 200
    assert attempts == 3
    assert delays == [0.5, 1.0]


def test_no_retry_for_400():
    attempts = 0

    def mock_api(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(400)

    with (
        httpx.Client(
            transport=httpx.MockTransport(mock_api)
        ) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        post_with_retry(
            client,
            {"query": "invalid"},
            sleep_fn=lambda seconds: None,
        )

    assert attempts == 1
