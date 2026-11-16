import json
from copy import deepcopy
from datetime import date

import polars as pl
import pytest

from tenderscope.history import build_history, select_runs
from tenderscope.history_download import download_inputs
from tenderscope.ingestion.ted_api import build_query
from tenderscope.transformations.silver import (
    BUYER_SCHEMA,
    CPV_SCHEMA,
    NOTICE_SCHEMA,
    transform_notices,
)


def entry(run="ted_first", day="2026-01-01", **kwargs):
    return {
        "run_id": run,
        "since": day,
        "until": day,
        "reason": "Reviewed fixture",
        **kwargs,
    }


def catalog(*runs, until="2026-01-01"):
    return {
        "schema_version": 1,
        "stream": "ted-poland-it",
        "since": "2026-01-01",
        "until": until,
        "runs": list(runs),
    }


def notice(identifier="A", day="2026-01-01", cpv="72000000"):
    return {
        "publication-number": identifier,
        "publication-date": day,
        "notice-title": {"eng": "Example"},
        "buyer-name": {"eng": ["Buyer A"]},
        "classification-cpv": [cpv],
        "notice-type": "competition",
    }


def write_run(root, run, notices):
    key = f"{run.get('prefix', 'runs')}/{run['run_id']}"
    raw, silver = root / "bronze" / key, root / "silver" / key
    raw.mkdir(parents=True)
    silver.mkdir(parents=True)
    (raw / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "completed",
                "query": build_query(
                    date.fromisoformat(run["since"]), date.fromisoformat(run["until"])
                ),
                "pages": [{"file": "page_001.json", "record_count": len(notices)}],
            }
        )
    )
    (raw / "page_001.json").write_text(json.dumps({"notices": notices}))
    rows = transform_notices(notices)
    for name, data, schema in zip(
        ("notice", "notice_cpv", "notice_buyer"),
        rows,
        (NOTICE_SCHEMA, CPV_SCHEMA, BUYER_SCHEMA),
        strict=True,
    ):
        pl.DataFrame(data, schema=schema).write_parquet(silver / f"{name}.parquet")
    (silver / "_SUCCESS.json").write_text(
        json.dumps(
            {
                "run_id": run["run_id"],
                "bronze_files": [f"{key}/manifest.json", f"{key}/page_001.json"],
                "silver_files": [
                    f"{key}/{name}.parquet"
                    for name in ("notice", "notice_cpv", "notice_buyer")
                ],
            }
        )
    )
    return raw, silver


def build(tmp_path, selection, output="history"):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(selection))
    return build_history(path, tmp_path / "inputs", tmp_path / output)


def test_history_keeps_lineage_empty_days_and_is_reproducible(tmp_path):
    first, second = entry(), entry("ted_empty", "2026-01-02")
    write_run(tmp_path / "inputs", first, [notice()])
    write_run(tmp_path / "inputs", second, [])
    selection = catalog(first, second, until="2026-01-02")
    result = build(tmp_path, selection)
    repeat = build(tmp_path, selection, "again")
    assert result == repeat
    assert result["notice_count"] == 1 and result["covered_days"] == 2
    daily = pl.read_parquet(tmp_path / "history/daily_summary.parquet")
    assert daily["notice_count"].to_list() == [1, 0]
    assert daily["complete"].to_list() == [True, True]
    assert daily["source_run_id"].to_list() == ["ted_first", "ted_empty"]
    notices = pl.read_parquet(tmp_path / "history/notice.parquet")
    assert notices["source_run_id"].to_list() == ["ted_first"]
    assert (tmp_path / "history/_SUCCESS.json").exists()
    with pytest.raises(FileExistsError):
        build(tmp_path, selection)


@pytest.mark.parametrize("empty_replacement", [False, True])
def test_reviewed_replacement_removes_old_rows_and_relationships(
    tmp_path, empty_replacement
):
    original = entry()
    replacement = entry(
        "ted_correction", prefix="corrections/review-1", supersedes="runs/ted_first"
    )
    write_run(tmp_path / "inputs", original, [notice("A"), notice("B")])
    write_run(
        tmp_path / "inputs",
        replacement,
        [] if empty_replacement else [notice("A", cpv="72200000")],
    )
    result = build(tmp_path, catalog(original, replacement))
    assert result["selected_runs"] == ["corrections/review-1/ted_correction"]
    assert result["notice_count"] == (0 if empty_replacement else 1)
    cpvs = pl.read_parquet(tmp_path / "history/notice_cpv.parquet")
    assert cpvs["cpv_code"].to_list() == ([] if empty_replacement else ["72200000"])
    assert "ted_first" not in str(result["source_sha256"])


@pytest.mark.parametrize(
    "case",
    [
        "gap",
        "overlap",
        "duplicate",
        "wrong_replacement",
        "missing_previous",
        "path",
        "partial_window",
        "date_format",
    ],
)
def test_invalid_catalog_is_rejected(case):
    first = entry()
    second = entry("ted_second", "2026-01-02")
    value = catalog(first, second, until="2026-01-02")
    if case == "gap":
        value["runs"] = [second]
    elif case == "overlap":
        second["since"] = "2026-01-01"
    elif case == "duplicate":
        value["runs"].append(deepcopy(first))
    elif case == "wrong_replacement":
        second["supersedes"] = "runs/ted_first"
    elif case == "missing_previous":
        second["supersedes"] = "runs/missing"
    elif case == "path":
        first["prefix"] = "../outside"
    elif case == "partial_window":
        first["until"] = "2026-01-02"
        second.update(supersedes="runs/ted_first")
    elif case == "date_format":
        first["since"] = "20260101"
    with pytest.raises(ValueError):
        select_runs(value)


@pytest.mark.parametrize(
    "case",
    [
        "partial",
        "query",
        "marker",
        "missing_file",
        "outside_date",
        "schema",
        "wrong_ids",
    ],
)
def test_ineligible_source_never_produces_snapshot(tmp_path, case):
    run = entry()
    raw, silver = write_run(tmp_path / "inputs", run, [notice()])
    if case in ("partial", "query"):
        value = json.loads((raw / "manifest.json").read_text())
        value["status" if case == "partial" else "query"] = (
            "partial" if case == "partial" else "buyer-country=DEU"
        )
        (raw / "manifest.json").write_text(json.dumps(value))
    elif case == "marker":
        (silver / "_SUCCESS.json").write_text('{"run_id": "ted_other"}')
    elif case == "missing_file":
        (silver / "notice_cpv.parquet").unlink()
    elif case == "outside_date":
        frame = pl.read_parquet(silver / "notice.parquet").with_columns(
            pl.lit(date(2026, 1, 2)).alias("publication_date")
        )
        frame.write_parquet(silver / "notice.parquet")
    elif case == "schema":
        frame = pl.read_parquet(silver / "notice.parquet").drop("title_en")
        frame.write_parquet(silver / "notice.parquet")
    elif case == "wrong_ids":
        (raw / "page_001.json").write_text(json.dumps({"notices": [notice("other")]}))
    with pytest.raises((ValueError, FileNotFoundError)):
        build(tmp_path, catalog(run))
    assert not (tmp_path / "history").exists()


def test_duplicate_ids_across_windows_require_review(tmp_path):
    first, second = entry(), entry("ted_second", "2026-01-02")
    write_run(tmp_path / "inputs", first, [notice()])
    write_run(tmp_path / "inputs", second, [notice(day="2026-01-02")])
    with pytest.raises(ValueError, match="multiple accepted windows"):
        build(tmp_path, catalog(first, second, until="2026-01-02"))


def test_downloader_reads_only_selected_files(tmp_path):
    first = entry()
    write_run(tmp_path / "cloud", first, [notice()])
    reads = []

    class Client:
        def __init__(self, path):
            self.path = path

        def get_file_system_client(self, name):
            return Client(self.path / name)

        def get_file_client(self, name):
            return Client(self.path / name)

        def download_file(self):
            reads.append(self.path)
            return self

        def readall(self):
            return self.path.read_bytes()

    destination = tmp_path / "download"
    download_inputs(Client(tmp_path / "cloud"), catalog(first), destination)
    assert len(reads) == 6
    assert all(path.is_relative_to(tmp_path / "cloud") for path in reads)
    with pytest.raises(FileExistsError):
        download_inputs(Client(tmp_path / "cloud"), catalog(first), destination)


def test_failed_output_has_no_success_marker(tmp_path, monkeypatch):
    run = entry()
    write_run(tmp_path / "inputs", run, [notice()])
    original = pl.DataFrame.write_parquet
    calls = 0

    def fail_second(frame, path, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Disk full")
        return original(frame, path, *args, **kwargs)

    monkeypatch.setattr(pl.DataFrame, "write_parquet", fail_second)
    with pytest.raises(OSError, match="Disk full"):
        build(tmp_path, catalog(run))
    assert (tmp_path / "history/notice.parquet").exists()
    assert not (tmp_path / "history/_SUCCESS.json").exists()


def test_source_change_during_read_is_rejected(tmp_path, monkeypatch):
    run = entry()
    raw, _ = write_run(tmp_path / "inputs", run, [notice()])
    original = pl.read_parquet

    def read_and_change(*args, **kwargs):
        result = original(*args, **kwargs)
        with (raw / "manifest.json").open("a") as output:
            output.write(" ")
        return result

    monkeypatch.setattr(pl, "read_parquet", read_and_change)
    with pytest.raises(ValueError, match="changed during"):
        build(tmp_path, catalog(run))
    assert not (tmp_path / "history").exists()


def test_history_accepts_completed_legacy_sort_with_same_filters(tmp_path):
    run = entry()
    raw, _ = write_run(tmp_path / "inputs", run, [notice()])
    path = raw / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["query"] = manifest["query"].replace(
        "SORT BY publication-number DESC", "SORT BY publication-date DESC"
    )
    path.write_text(json.dumps(manifest))
    assert build(tmp_path, catalog(run))["notice_count"] == 1

    manifest["query"] = manifest["query"].replace(
        "buyer-country=POL", "buyer-country=DEU"
    )
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="query"):
        build(tmp_path, catalog(run), "wrong-filter")
