"""Build a reviewed historical snapshot from complete run-based Silver datasets."""

import argparse
import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from tenderscope.ingestion.ted_api import build_query
from tenderscope.ingestion.ted_pages import atomic_write
from tenderscope.quality.silver import validate_silver
from tenderscope.transformations.bronze_reader import load_bronze_run
from tenderscope.transformations.gold import build_gold

TABLES = ("notice", "notice_buyer", "notice_cpv")
RUN_ID = re.compile(r"^ted_[A-Za-z0-9_-]+$")
PREFIX = re.compile(r"^[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*$")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def parse_day(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Catalog dates must use YYYY-MM-DD")
    return parsed


def select_runs(catalog: dict) -> list[dict]:
    """Resolve explicit whole-window replacements; never choose by arrival time."""
    if not isinstance(catalog, dict):
        raise TypeError("Catalog must be an object")
    if type(catalog.get("schema_version")) is not int or catalog["schema_version"] != 1:
        raise ValueError("Unsupported history catalog version")
    if catalog.get("stream") != "ted-poland-it":
        raise ValueError("History currently supports only ted-poland-it")
    start, end = (
        parse_day(catalog["since"]),
        parse_day(catalog["until"]),
    )
    if start > end:
        raise ValueError("Invalid catalog date range")
    entries = catalog.get("runs")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Catalog must contain reviewed runs")
    active = {}
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError("Invalid catalog entry")
        run_id, prefix = entry.get("run_id", ""), entry.get("prefix", "runs")
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise ValueError("Invalid run ID")
        if not isinstance(prefix, str) or not PREFIX.fullmatch(prefix):
            raise ValueError("Invalid storage prefix")
        key = f"{prefix}/{run_id}"
        if key in seen:
            raise ValueError(f"Duplicate catalog run: {key}")
        seen.add(key)
        lower, upper = (
            parse_day(entry["since"]),
            parse_day(entry["until"]),
        )
        if lower > upper or lower < start or upper > end:
            raise ValueError(f"Run outside catalog range: {key}")
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            raise ValueError("Each selection needs a review reason")
        supersedes = entry.get("supersedes")
        if supersedes is not None:
            previous = active.get(supersedes)
            if previous is None:
                raise ValueError("Replacement must name an active earlier run")
            if (previous["since"], previous["until"]) != (
                entry["since"],
                entry["until"],
            ):
                raise ValueError("Replacement must cover the exact previous window")
            del active[supersedes]
        active[key] = {**entry, "prefix": prefix, "key": key}
    selected = sorted(active.values(), key=lambda item: item["since"])
    expected = start
    for entry in selected:
        if parse_day(entry["since"]) != expected:
            raise ValueError(
                f"Gap or overlap before {entry['key']}; expected {expected}"
            )
        expected = parse_day(entry["until"]) + timedelta(days=1)
    if expected != end + timedelta(days=1):
        raise ValueError("Catalog does not cover its full date range")
    return selected


def source_path(root: Path, relative: str) -> Path:
    base = root.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base):
        raise ValueError("Source path escapes the input root")
    return path


def source_files(root: Path, entry: dict) -> list[Path]:
    key = entry["key"]
    raw = source_path(root, f"bronze/{key}")
    silver = source_path(root, f"silver/{key}")
    manifest = read_json(raw / "manifest.json")
    marker = read_json(silver / "_SUCCESS.json")
    if marker.get("run_id") != entry["run_id"]:
        raise ValueError("Completion marker belongs to another run")
    expected_query = build_query(parse_day(entry["since"]), parse_day(entry["until"]))
    if manifest.get("query") != expected_query:
        raise ValueError("Catalog window or stream differs from the source query")
    if manifest.get("status") != "completed":
        raise ValueError("History rejects partial runs")
    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("Missing Bronze pages")
    page_names = [f"page_{i:03d}.json" for i in range(1, len(pages) + 1)]
    if [page.get("file") for page in pages] != page_names:
        raise ValueError("Invalid Bronze page sequence")
    expected_bronze = {f"{key}/{name}" for name in ["manifest.json", *page_names]}
    expected_silver = {f"{key}/{name}.parquet" for name in TABLES}
    if not expected_bronze.issubset(marker.get("bronze_files", [])):
        raise ValueError("Completion marker is missing Bronze files")
    if set(marker.get("silver_files", [])) != expected_silver:
        raise ValueError("Completion marker does not describe the Silver contract")
    relative = [f"bronze/{key}/{name}" for name in ["manifest.json", *page_names]]
    relative += [f"silver/{key}/{name}.parquet" for name in TABLES]
    relative += [f"silver/{key}/_SUCCESS.json"]
    return [source_path(root, name) for name in relative]


def fingerprints(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root.resolve()).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in paths
    }


def build_history(catalog_path: Path, source_root: Path, output: Path) -> dict:
    catalog_bytes = catalog_path.read_bytes()
    catalog = json.loads(catalog_bytes)
    selected = select_runs(catalog)
    frames = {name: [] for name in TABLES}
    evidence = {}
    coverage = []
    for entry in selected:
        paths = source_files(source_root, entry)
        before = fingerprints(source_root, paths)
        raw = source_path(source_root, f"bronze/{entry['key']}")
        silver = source_path(source_root, f"silver/{entry['key']}")
        bronze = load_bronze_run(raw)
        validate_silver(raw, silver_dir=silver)
        batch = {name: pl.read_parquet(silver / f"{name}.parquet") for name in TABLES}
        lower, upper = (
            parse_day(entry["since"]),
            parse_day(entry["until"]),
        )
        notices = batch["notice"]
        if notices.filter(~pl.col("publication_date").is_between(lower, upper)).height:
            raise ValueError("Notice date falls outside the selected window")
        if set(notices["notice_id"]) != {
            item.get("publication-number") for item in bronze
        }:
            raise ValueError("Bronze/Silver notice IDs differ")
        if paths != source_files(source_root, entry) or before != fingerprints(
            source_root, paths
        ):
            raise ValueError("Source files changed during history construction")
        evidence.update(before)
        for name in TABLES:
            frames[name].append(
                batch[name].with_columns(
                    pl.lit(entry["run_id"]).alias("source_run_id"),
                    pl.lit(entry["prefix"]).alias("source_prefix"),
                )
            )
        current = lower
        while current <= upper:
            coverage.append(
                {
                    "publication_date": current,
                    "source_run_id": entry["run_id"],
                    "source_prefix": entry["prefix"],
                    "complete": True,
                }
            )
            current += timedelta(days=1)
    merged = {name: pl.concat(parts) for name, parts in frames.items()}
    if merged["notice"]["notice_id"].n_unique() != merged["notice"].height:
        raise ValueError(
            "Notice ID occurs in multiple accepted windows; review the catalog"
        )
    for name, keys in (
        ("notice", ["notice_id"]),
        ("notice_buyer", ["notice_id", "buyer_name"]),
        ("notice_cpv", ["notice_id", "cpv_code"]),
    ):
        merged[name] = merged[name].sort(keys)
    models = build_gold(merged["notice"], merged["notice_buyer"], merged["notice_cpv"])
    calendar = pl.DataFrame(coverage)
    models["daily_summary"] = (
        calendar.join(models["daily_summary"], on="publication_date", how="left")
        .with_columns(
            pl.col("notice_count", "unique_buyers", "unique_cpv_codes").fill_null(0)
        )
        .sort("publication_date")
    )
    result = {
        "schema_version": 1,
        "stream": catalog["stream"],
        "since": catalog["since"],
        "until": catalog["until"],
        "catalog_sha256": hashlib.sha256(catalog_bytes).hexdigest(),
        "selected_runs": [entry["key"] for entry in selected],
        "source_sha256": evidence,
        "notice_count": merged["notice"].height,
        "covered_days": len(coverage),
    }
    # Never replace a previously built snapshot. Consumers require _SUCCESS.json.
    output.mkdir(parents=True, exist_ok=False)
    for name, frame in {**merged, **models}.items():
        frame.write_parquet(output / f"{name}.parquet")
    (output / "catalog.json").write_bytes(catalog_bytes)
    result["output_sha256"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.iterdir())
        if path.is_file()
    }
    atomic_write(output / "_SUCCESS.json", json.dumps(result, indent=2).encode("utf-8"))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_history(args.catalog, args.source_root, args.output)
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("notice_count", "covered_days", "selected_runs")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
