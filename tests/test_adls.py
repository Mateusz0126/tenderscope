import json
from datetime import UTC, datetime

import pytest

from tenderscope.storage.adls import (
    publish_run_to_adls,
    publish_run_with_client,
)


class FakeDirectoryClient:
    def create_directory(self):
        return None


class FakeFileClient:
    def __init__(self, files, path, fail_on=None):
        self.files = files
        self.path = path
        self.fail_on = fail_on

    def upload_data(self, data, *, overwrite):
        if self.path == self.fail_on:
            raise RuntimeError("simulated upload failure")

        if hasattr(data, "read"):
            data = data.read()

        assert overwrite is True
        self.files[self.path] = bytes(data)


class FakeFileSystemClient:
    def __init__(self, fail_on=None):
        self.files = {}
        self.fail_on = fail_on

    def get_directory_client(self, path):
        return FakeDirectoryClient()

    def get_file_client(self, path):
        return FakeFileClient(self.files, path, self.fail_on)


class FakeServiceClient:
    def __init__(self, silver_fail_on=None):
        self.file_systems = {
            "bronze": FakeFileSystemClient(),
            "silver": FakeFileSystemClient(silver_fail_on),
        }

    def get_file_system_client(self, file_system):
        return self.file_systems[file_system]


def create_run_files(tmp_path):
    run_dir = tmp_path / "data/raw/ted_test"
    silver_dir = tmp_path / "data/silver/ted_test"
    run_dir.mkdir(parents=True)
    silver_dir.mkdir(parents=True)

    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (run_dir / "page_001.json").write_text("{}", encoding="utf-8")
    (silver_dir / "notice.parquet").write_bytes(b"notice")
    (silver_dir / "notice_cpv.parquet").write_bytes(b"cpv")
    (silver_dir / "notice_buyer.parquet").write_bytes(b"buyer")

    return run_dir, silver_dir


def test_publish_run_uploads_bronze_silver_and_marker(tmp_path):
    run_dir, silver_dir = create_run_files(tmp_path)
    service = FakeServiceClient()

    result = publish_run_with_client(
        service,
        run_dir,
        silver_dir,
        now=lambda: datetime(2026, 11, 14, 19, 0, tzinfo=UTC),
    )

    bronze_files = service.file_systems["bronze"].files
    silver_files = service.file_systems["silver"].files

    assert set(bronze_files) == {
        "runs/ted_test/manifest.json",
        "runs/ted_test/page_001.json",
    }
    assert set(silver_files) == {
        "runs/ted_test/notice.parquet",
        "runs/ted_test/notice_cpv.parquet",
        "runs/ted_test/notice_buyer.parquet",
        "runs/ted_test/_SUCCESS.json",
    }

    marker = json.loads(silver_files["runs/ted_test/_SUCCESS.json"])
    assert marker["run_id"] == "ted_test"
    assert marker["published_at_utc"] == "2026-11-14T19:00:00+00:00"
    assert result == {
        "run_id": "ted_test",
        "bronze_files": 2,
        "silver_files": 3,
        "success_marker": "runs/ted_test/_SUCCESS.json",
    }


def test_publish_failure_does_not_create_success_marker(tmp_path):
    run_dir, silver_dir = create_run_files(tmp_path)
    service = FakeServiceClient(
        silver_fail_on="runs/ted_test/notice_cpv.parquet"
    )

    with pytest.raises(RuntimeError, match="simulated upload failure"):
        publish_run_with_client(service, run_dir, silver_dir)

    assert (
        "runs/ted_test/_SUCCESS.json"
        not in service.file_systems["silver"].files
    )


def test_publish_rejects_invalid_storage_account(tmp_path):
    run_dir, silver_dir = create_run_files(tmp_path)

    with pytest.raises(ValueError, match="Invalid Azure Storage account"):
        publish_run_to_adls("INVALID_ACCOUNT", run_dir, silver_dir)
