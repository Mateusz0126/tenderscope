
import argparse
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

import httpx

from tenderscope.ingestion.ted_api import build_query
from tenderscope.ingestion.ted_pages import run_download
from tenderscope.quality.silver import validate_silver
from tenderscope.storage.adls import publish_run_to_adls
from tenderscope.transformations.bronze_reader import load_bronze_run
from tenderscope.transformations.silver import write_silver


def run_pipeline(
    client: httpx.Client,
    run_dir: Path,
    *,
    query: str | None,
    max_pages: int,
    allow_partial: bool = False,
    publisher: Callable[[Path, Path], dict[str, object]] | None = None,
) -> dict:
    start_time = time.monotonic()

    print("\n=== TENDERSCOPE PIPELINE ===")

    # STEP 1: INGESTION
    print("\n[1/4] TED ingestion")

    run_download(
        client,
        run_dir,
        query=query,
        max_pages=max_pages,
    )

    # STEP 2: BRONZE VALIDATION
    print("\n[2/4] Bronze validation")

    notices = load_bronze_run(
        run_dir,
        allow_partial=allow_partial,
    )

    print(f"Bronze records: {len(notices)}")

    # STEP 3: SILVER TRANSFORMATION
    print("\n[3/4] Silver transformation")

    silver_metrics = write_silver(
        run_dir,
        allow_partial=allow_partial,
    )

    print("Silver metrics:", silver_metrics)

    # STEP 4: SILVER QUALITY
    print("\n[4/4] Silver quality gate")

    quality_metrics = validate_silver(
        run_dir,
        allow_partial=allow_partial,
    )

    storage_metrics = None

    if publisher is not None:
        print("\n[5/5] ADLS publication")
        silver_dir = Path("data/silver") / run_dir.name
        storage_metrics = publisher(run_dir, silver_dir)
        print("ADLS metrics:", storage_metrics)

    duration = round(time.monotonic() - start_time, 2)

    results = {
        "run_id": run_dir.name,
        "bronze_records": len(notices),
        "silver_metrics": silver_metrics,
        "quality_metrics": quality_metrics,
        "storage_metrics": storage_metrics,
        "duration_seconds": duration,
    }

    print("\n=== PIPELINE SUCCESS ===")
    print("Run:", run_dir.name)
    print("Duration:", duration, "seconds")
    print("Quality:", quality_metrics)

    return results


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
    )

    parser.add_argument(
        "--resume",
        type=Path,
    )

    parser.add_argument(
        "--allow-partial",
        action="store_true",
    )

    parser.add_argument(
        "--storage-account",
        default=os.environ.get("TENDERSCOPE_STORAGE_ACCOUNT"),
    )

    parser.add_argument(
        "--storage-prefix",
        default=os.environ.get("TENDERSCOPE_STORAGE_PREFIX", "runs"),
    )

    args = parser.parse_args()

    if args.resume:
        run_dir = args.resume
        query = None
    else:
        since = (
            datetime.now(UTC).date()
            - timedelta(days=45)
        )

        query = build_query(since)

        run_id = datetime.now(UTC).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )

        run_dir = Path("data/raw") / f"ted_{run_id}"

    publisher = None

    if args.storage_account:
        publisher = partial(
            publish_run_to_adls,
            args.storage_account,
            prefix=args.storage_prefix,
        )

    with httpx.Client(timeout=30.0) as client:
        run_pipeline(
            client,
            run_dir,
            query=query,
            max_pages=args.max_pages,
            allow_partial=args.allow_partial,
            publisher=publisher,
        )


if __name__ == "__main__":
    main()
