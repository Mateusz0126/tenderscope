
import argparse
import os
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path

import httpx

from tenderscope.ingestion.ted_api import build_query, resolve_date_window
from tenderscope.ingestion.ted_pages import run_download
from tenderscope.orchestration.state import (
    DEFAULT_STATE_STREAM,
    DateWindow,
    resolve_incremental_window,
)
from tenderscope.quality.silver import validate_silver
from tenderscope.storage.adls import publish_run_to_adls
from tenderscope.storage.adls_state import (
    commit_pipeline_state,
    read_pipeline_state,
)
from tenderscope.transformations.bronze_reader import load_bronze_run
from tenderscope.transformations.gold import write_gold
from tenderscope.transformations.silver import write_silver


def run_pipeline(
    client: httpx.Client,
    run_dir: Path,
    *,
    query: str | None,
    max_pages: int,
    allow_partial: bool = False,
    publisher: Callable[[Path, Path, Path], dict[str, object]] | None = None,
    state_committer: Callable[[str], dict[str, object]] | None = None,
) -> dict:
    if state_committer is not None and publisher is None:
        raise ValueError("Durable state requires successful ADLS publication")

    if state_committer is not None and allow_partial:
        raise ValueError("Durable state cannot advance a partial ingestion")

    start_time = time.monotonic()
    total_steps = 5 + int(publisher is not None) + int(
        state_committer is not None
    )

    def print_step(number: int, label: str) -> None:
        print(f"\n[{number}/{total_steps}] {label}")

    print("\n=== TENDERSCOPE PIPELINE ===")

    # STEP 1: INGESTION
    print_step(1, "TED ingestion")

    run_download(
        client,
        run_dir,
        query=query,
        max_pages=max_pages,
    )

    # STEP 2: BRONZE VALIDATION
    print_step(2, "Bronze validation")

    notices = load_bronze_run(
        run_dir,
        allow_partial=allow_partial,
    )

    print(f"Bronze records: {len(notices)}")

    # STEP 3: SILVER TRANSFORMATION
    print_step(3, "Silver transformation")

    silver_metrics = write_silver(
        run_dir,
        allow_partial=allow_partial,
    )

    print("Silver metrics:", silver_metrics)

    # STEP 4: SILVER QUALITY
    print_step(4, "Silver quality gate")

    quality_metrics = validate_silver(
        run_dir,
        allow_partial=allow_partial,
    )

    print_step(5, "Gold analytical models")
    silver_dir = Path("data/silver") / run_dir.name
    gold_dir = Path("data/gold") / run_dir.name
    gold_metrics = write_gold(silver_dir, gold_dir)

    print("Gold metrics:", gold_metrics)

    storage_metrics = None

    if publisher is not None:
        print_step(6, "ADLS publication")
        storage_metrics = publisher(run_dir, silver_dir, gold_dir)
        print("ADLS metrics:", storage_metrics)

    state_metrics = None

    if state_committer is not None:
        print_step(7, "Durable state commit")
        state_metrics = state_committer(run_dir.name)
        print("State metrics:", state_metrics)

    duration = round(time.monotonic() - start_time, 2)

    results = {
        "run_id": run_dir.name,
        "bronze_records": len(notices),
        "silver_metrics": silver_metrics,
        "quality_metrics": quality_metrics,
        "gold_metrics": gold_metrics,
        "storage_metrics": storage_metrics,
        "state_metrics": state_metrics,
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
        "--since",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Inclusive publication-date lower bound.",
    )

    parser.add_argument(
        "--until",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="Inclusive publication-date upper bound.",
    )

    parser.add_argument(
        "--storage-account",
        default=os.environ.get("TENDERSCOPE_STORAGE_ACCOUNT"),
    )

    parser.add_argument(
        "--storage-prefix",
        default=os.environ.get("TENDERSCOPE_STORAGE_PREFIX", "runs"),
    )

    parser.add_argument(
        "--state-policy",
        choices=("off", "enforce"),
        default="off",
        help=(
            "Use a durable ADLS watermark and reject date gaps or overlaps."
        ),
    )

    parser.add_argument(
        "--state-stream",
        default=os.environ.get(
            "TENDERSCOPE_STATE_STREAM",
            DEFAULT_STATE_STREAM,
        ),
        help="Logical incremental stream stored in the ADLS control container.",
    )

    parser.add_argument(
        "--state-prefix",
        default=os.environ.get("TENDERSCOPE_STATE_PREFIX", "state"),
    )

    args = parser.parse_args()

    since_arg = args.since
    until_arg = args.until

    if args.resume and (since_arg is not None or until_arg is not None):
        parser.error("--since/--until cannot be used with --resume")

    if args.resume and args.state_policy != "off":
        parser.error("Durable state cannot be used with --resume")

    if args.state_policy == "enforce" and not args.storage_account:
        parser.error("Durable state requires --storage-account")

    if args.state_policy == "enforce" and args.allow_partial:
        parser.error("Durable state cannot advance a partial ingestion")

    state_snapshot = None
    state_window: DateWindow | None = None

    if args.resume:
        run_dir = args.resume
        query = None
    else:
        today = datetime.now(UTC).date()

        if args.state_policy == "enforce":
            state_snapshot = read_pipeline_state(
                args.storage_account,
                args.state_stream,
                prefix=args.state_prefix,
            )

            try:
                state_window = resolve_incremental_window(
                    snapshot=state_snapshot,
                    requested_since=since_arg,
                    requested_until=until_arg,
                    today=today,
                )
            except ValueError as error:
                parser.error(str(error))

            since, until = state_window.since, state_window.until
        else:
            try:
                since, until = resolve_date_window(
                    since=since_arg,
                    until=until_arg,
                    today=today,
                )
            except ValueError as error:
                parser.error(str(error))

        query = build_query(since, until)

        run_id = datetime.now(UTC).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )

        run_dir = Path("data/raw") / f"ted_{run_id}"

    publisher = None
    state_committer = None

    if args.storage_account:
        publisher = partial(
            publish_run_to_adls,
            args.storage_account,
            prefix=args.storage_prefix,
        )

    if state_snapshot is not None and state_window is not None:
        state_committer = partial(
            commit_pipeline_state,
            args.storage_account,
            args.state_stream,
            state_snapshot,
            state_window,
            prefix=args.state_prefix,
        )

    with httpx.Client(timeout=30.0) as client:
        run_pipeline(
            client,
            run_dir,
            query=query,
            max_pages=args.max_pages,
            allow_partial=args.allow_partial,
            publisher=publisher,
            state_committer=state_committer,
        )


if __name__ == "__main__":
    main()

