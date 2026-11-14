import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Protocol

from azure.core.exceptions import ResourceExistsError
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

STORAGE_ACCOUNT_PATTERN = re.compile(r"^[a-z0-9]{3,24}$")


class FileClient(Protocol):
    def upload_data(
        self,
        data: bytes | IO[bytes],
        *,
        overwrite: bool,
    ) -> object: ...


class DirectoryClient(Protocol):
    def create_directory(self) -> object: ...


class FileSystemClient(Protocol):
    def get_directory_client(self, path: str) -> DirectoryClient: ...

    def get_file_client(self, path: str) -> FileClient: ...


class ServiceClient(Protocol):
    def get_file_system_client(
        self,
        file_system: str,
    ) -> FileSystemClient: ...


def normalize_prefix(prefix: str) -> str:
    parts = [part for part in prefix.strip("/").split("/") if part]

    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("ADLS prefix must be a relative path")

    return "/".join(parts)


def validate_account_name(account_name: str) -> None:
    if not STORAGE_ACCOUNT_PATTERN.fullmatch(account_name):
        raise ValueError("Invalid Azure Storage account name")


def list_local_files(directory: Path) -> tuple[Path, ...]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Missing local directory: {directory}")

    files = tuple(
        sorted(
            path
            for path in directory.rglob("*")
            if path.is_file()
        )
    )

    if not files:
        raise ValueError(f"No files found in {directory}")

    return files


def ensure_directory(
    file_system: FileSystemClient,
    path: str,
) -> None:
    current = ""

    for part in path.split("/"):
        current = f"{current}/{part}" if current else part
        directory = file_system.get_directory_client(current)

        try:
            directory.create_directory()
        except ResourceExistsError:
            pass


def upload_files(
    file_system: FileSystemClient,
    source_directory: Path,
    target_directory: str,
) -> list[str]:
    ensure_directory(file_system, target_directory)
    uploaded = []

    for local_path in list_local_files(source_directory):
        relative_path = local_path.relative_to(source_directory).as_posix()
        remote_path = f"{target_directory}/{relative_path}"
        file_client = file_system.get_file_client(remote_path)

        with local_path.open("rb") as data:
            file_client.upload_data(data, overwrite=True)

        uploaded.append(remote_path)

    return uploaded


def publish_run_with_client(
    service_client: ServiceClient,
    run_dir: Path,
    silver_dir: Path,
    *,
    prefix: str = "runs",
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    if run_dir.name != silver_dir.name:
        raise ValueError("Bronze and Silver run IDs must match")

    normalized_prefix = normalize_prefix(prefix)
    target_directory = f"{normalized_prefix}/{run_dir.name}"

    bronze = service_client.get_file_system_client("bronze")
    silver = service_client.get_file_system_client("silver")

    bronze_files = upload_files(bronze, run_dir, target_directory)
    silver_files = upload_files(silver, silver_dir, target_directory)

    marker_path = f"{target_directory}/_SUCCESS.json"
    marker = {
        "run_id": run_dir.name,
        "published_at_utc": now().astimezone(UTC).isoformat(),
        "bronze_files": bronze_files,
        "silver_files": silver_files,
    }

    silver.get_file_client(marker_path).upload_data(
        json.dumps(marker, indent=2).encode("utf-8"),
        overwrite=True,
    )

    return {
        "run_id": run_dir.name,
        "bronze_files": len(bronze_files),
        "silver_files": len(silver_files),
        "success_marker": marker_path,
    }


def publish_run_to_adls(
    account_name: str,
    run_dir: Path,
    silver_dir: Path,
    *,
    prefix: str = "runs",
) -> dict[str, object]:
    validate_account_name(account_name)

    credential = DefaultAzureCredential()
    service_client = DataLakeServiceClient(
        account_url=f"https://{account_name}.dfs.core.windows.net",
        credential=credential,
    )

    try:
        return publish_run_with_client(
            service_client,
            run_dir,
            silver_dir,
            prefix=prefix,
        )
    finally:
        service_client.close()
        credential.close()
