from datetime import UTC, date, datetime
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from azure.core import MatchConditions
from azure.core.exceptions import (
    ResourceExistsError,
    ResourceModifiedError,
    ResourceNotFoundError,
)
from azure.storage.filedatalake import DataLakeServiceClient

from tenderscope.orchestration.state import (
    DateWindow,
    PipelineState,
    StateConflictError,
    StateSnapshot,
)
from tenderscope.storage.adls_state import (
    commit_state_with_client,
    read_state_with_client,
)


class FakeDirectoryClient:
    def create_directory(self):
        return None


class FakeDownload:
    def __init__(self, content, etag):
        self.content = content
        self.properties = SimpleNamespace(etag=etag)

    def readall(self):
        return self.content


class FakeStateFileClient:
    def __init__(self, file_system, path):
        self.file_system = file_system
        self.path = path

    def download_file(self):
        if self.path not in self.file_system.files:
            raise ResourceNotFoundError("missing")

        return FakeDownload(
            self.file_system.files[self.path],
            self.file_system.etag,
        )

    def upload_data(
        self,
        data,
        *,
        overwrite,
        etag=None,
        match_condition=None,
    ):
        exists = self.path in self.file_system.files

        if etag is not None:
            assert match_condition == MatchConditions.IfNotModified

            if etag != self.file_system.etag:
                raise ResourceModifiedError("etag mismatch")

        if match_condition == MatchConditions.IfMissing:
            assert etag is None

            if exists:
                raise ResourceExistsError("already exists")

        assert overwrite is True
        self.file_system.files[self.path] = bytes(data)
        self.file_system.etag = '"etag-next"'


class FakeFileSystemClient:
    def __init__(self):
        self.files = {}
        self.etag = '"etag-1"'

    def get_directory_client(self, path):
        return FakeDirectoryClient()

    def get_file_client(self, path):
        return FakeStateFileClient(self, path)


class FakeServiceClient:
    def __init__(self):
        self.control = FakeFileSystemClient()

    def get_file_system_client(self, file_system):
        assert file_system == "control"
        return self.control


def make_state(last_completed_date=date(2026, 11, 11)):
    return PipelineState(
        stream="ted-poland-it",
        last_completed_date=last_completed_date,
        last_run_id="ted_previous",
        updated_at_utc=datetime(2026, 11, 13, 20, 0, tzinfo=UTC),
    )


def test_read_missing_state_returns_empty_snapshot():
    service = FakeServiceClient()

    result = read_state_with_client(service, "ted-poland-it")

    assert result == StateSnapshot(state=None, etag=None)


def test_read_state_returns_content_and_etag():
    service = FakeServiceClient()
    state = make_state()
    service.control.files["state/ted-poland-it.json"] = state.to_json()

    result = read_state_with_client(service, "ted-poland-it")

    assert result == StateSnapshot(state=state, etag='"etag-1"')


def test_first_commit_creates_versioned_state():
    service = FakeServiceClient()

    result = commit_state_with_client(
        service,
        "ted-poland-it",
        StateSnapshot(state=None, etag=None),
        DateWindow(
            since=date(2026, 11, 10),
            until=date(2026, 11, 11),
        ),
        "ted_current",
        now=lambda: datetime(2026, 11, 14, 20, 0, tzinfo=UTC),
    )

    stored = PipelineState.from_json(service.control.files["state/ted-poland-it.json"])
    assert stored.last_completed_date == date(2026, 11, 11)
    assert stored.last_run_id == "ted_current"
    assert result["etag_precondition"] is False


def test_existing_state_commit_uses_etag_precondition():
    service = FakeServiceClient()
    previous = make_state()
    service.control.files["state/ted-poland-it.json"] = previous.to_json()

    result = commit_state_with_client(
        service,
        "ted-poland-it",
        StateSnapshot(state=previous, etag='"etag-1"'),
        DateWindow(
            since=date(2026, 11, 12),
            until=date(2026, 11, 12),
        ),
        "ted_current",
    )

    assert result["previous_completed_date"] == "2026-11-11"
    assert result["last_completed_date"] == "2026-11-12"
    assert result["etag_precondition"] is True


def test_stale_etag_is_rejected_without_overwrite():
    service = FakeServiceClient()
    previous = make_state()
    original = previous.to_json()
    service.control.files["state/ted-poland-it.json"] = original

    with pytest.raises(StateConflictError, match="refusing to overwrite"):
        commit_state_with_client(
            service,
            "ted-poland-it",
            StateSnapshot(state=previous, etag='"stale"'),
            DateWindow(
                since=date(2026, 11, 12),
                until=date(2026, 11, 12),
            ),
            "ted_current",
        )

    assert service.control.files["state/ted-poland-it.json"] == original


def test_concurrent_bootstrap_is_rejected():
    service = FakeServiceClient()
    service.control.files["state/ted-poland-it.json"] = make_state().to_json()

    with pytest.raises(StateConflictError, match="refusing to overwrite"):
        commit_state_with_client(
            service,
            "ted-poland-it",
            StateSnapshot(state=None, etag=None),
            DateWindow(
                since=date(2026, 11, 10),
                until=date(2026, 11, 11),
            ),
            "ted_current",
        )


@pytest.mark.parametrize(
    ("snapshot", "header", "expected"),
    [
        (StateSnapshot(None, None), "If-None-Match", "*"),
        (StateSnapshot(make_state(), '"previous"'), "If-Match", '"previous"'),
    ],
)
def test_state_commit_sends_conditional_request_through_azure_sdk(
    monkeypatch, snapshot, header, expected
):
    requests_seen = []

    def send(_session, request, **_kwargs):
        query = parse_qs(urlsplit(request.url).query)
        action = query.get("action", [None])[0]
        response = requests.Response()
        response.request = request
        response.raw = BytesIO()
        response.headers["ETag"] = '"new"'
        response.status_code = {None: 201, "append": 202, "flush": 200}[action]
        response._content = b""
        requests_seen.append(request)
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    with DataLakeServiceClient("https://example.dfs.core.windows.net") as service:
        commit_state_with_client(
            service,
            "ted-poland-it",
            snapshot,
            DateWindow(date(2026, 11, 12), date(2026, 11, 12)),
            "ted_current",
        )

    _, create, append, flush = requests_seen
    assert create.method == "PUT"
    assert create.headers[header] == expected
    assert PipelineState.from_json(append.body).last_run_id == "ted_current"
    assert flush.headers["If-Match"] == '"new"'
