from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from azure.core import MatchConditions
from azure.core.exceptions import (
    ResourceExistsError,
    ResourceModifiedError,
    ResourceNotFoundError,
)
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

from tenderscope.orchestration.state import (
    DateWindow,
    PipelineState,
    StateConflictError,
    StateSnapshot,
    advance_state,
    validate_stream,
)
from tenderscope.storage.adls import (
    ServiceClient,
    ensure_directory,
    normalize_prefix,
    validate_account_name,
)


class Download(Protocol):
    properties: object

    def readall(self) -> bytes: ...


class StateFileClient(Protocol):
    def download_file(self) -> Download: ...

    def upload_data(
        self,
        data: bytes,
        *,
        overwrite: bool,
        **kwargs: object,
    ) -> object: ...


def state_path(stream: str, *, prefix: str = "state") -> str:
    validate_stream(stream)
    return f"{normalize_prefix(prefix)}/{stream}.json"


def read_state_with_client(
    service_client: ServiceClient,
    stream: str,
    *,
    prefix: str = "state",
) -> StateSnapshot:
    control = service_client.get_file_system_client("control")
    file_client = control.get_file_client(state_path(stream, prefix=prefix))

    try:
        download = file_client.download_file()  # type: ignore[attr-defined]
    except ResourceNotFoundError:
        return StateSnapshot(state=None, etag=None)

    properties = download.properties
    etag = getattr(properties, "etag", None)

    if not isinstance(etag, str) or not etag:
        raise RuntimeError("State download did not include an ETag")

    state = PipelineState.from_json(download.readall())

    if state.stream != stream:
        raise ValueError("State file stream does not match its path")

    return StateSnapshot(state=state, etag=etag)


def commit_state_with_client(
    service_client: ServiceClient,
    stream: str,
    snapshot: StateSnapshot,
    window: DateWindow,
    run_id: str,
    *,
    prefix: str = "state",
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    path = state_path(stream, prefix=prefix)
    control = service_client.get_file_system_client("control")
    directory = path.rsplit("/", maxsplit=1)[0]
    ensure_directory(control, directory)
    file_client: StateFileClient = control.get_file_client(path)  # type: ignore[assignment]
    state = advance_state(
        stream=stream,
        previous=snapshot.state,
        window=window,
        run_id=run_id,
        now=now(),
    )

    try:
        if snapshot.etag is None:
            file_client.upload_data(state.to_json(), overwrite=False)
        else:
            file_client.upload_data(
                state.to_json(),
                overwrite=True,
                etag=snapshot.etag,
                match_condition=MatchConditions.IfNotModified,
            )
    except (ResourceExistsError, ResourceModifiedError) as error:
        raise StateConflictError(
            "Durable state changed during this execution; refusing to overwrite it"
        ) from error

    return {
        "stream": stream,
        "state_path": path,
        "previous_completed_date": (
            snapshot.state.last_completed_date.isoformat()
            if snapshot.state is not None
            else None
        ),
        "last_completed_date": state.last_completed_date.isoformat(),
        "etag_precondition": snapshot.etag is not None,
    }


def read_pipeline_state(
    account_name: str,
    stream: str,
    *,
    prefix: str = "state",
) -> StateSnapshot:
    validate_account_name(account_name)
    credential = DefaultAzureCredential()
    service_client = DataLakeServiceClient(
        account_url=f"https://{account_name}.dfs.core.windows.net",
        credential=credential,
    )

    try:
        return read_state_with_client(
            service_client,
            stream,
            prefix=prefix,
        )
    finally:
        service_client.close()
        credential.close()


def commit_pipeline_state(
    account_name: str,
    stream: str,
    snapshot: StateSnapshot,
    window: DateWindow,
    run_id: str,
    *,
    prefix: str = "state",
) -> dict[str, object]:
    validate_account_name(account_name)
    credential = DefaultAzureCredential()
    service_client = DataLakeServiceClient(
        account_url=f"https://{account_name}.dfs.core.windows.net",
        credential=credential,
    )

    try:
        return commit_state_with_client(
            service_client,
            stream,
            snapshot,
            window,
            run_id,
            prefix=prefix,
        )
    finally:
        service_client.close()
        credential.close()
