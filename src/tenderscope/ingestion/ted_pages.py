
import argparse
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from tenderscope.ingestion.ted_api import (
    SEARCH_FIELDS,
    TED_URL,
    build_query,
)

PAGE_SIZE = 50
MAX_PAGES = 2
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def post_with_retry(
    client: httpx.Client,
    payload: dict,
    *,
    max_retries: int = 3,
    base_delay: float = 0.5,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    for attempt in range(max_retries + 1):
        try:
            response = client.post(TED_URL, json=payload)
        except httpx.RequestError:
            if attempt == max_retries:
                raise

            sleep_fn(base_delay * (2**attempt))
            continue

        if (
            response.status_code in RETRYABLE_STATUSES
            and attempt < max_retries
        ):
            retry_after = response.headers.get("Retry-After")

            if retry_after and retry_after.isdecimal():
                delay = float(retry_after)
            else:
                delay = base_delay * (2**attempt)

            sleep_fn(delay)
            continue

        response.raise_for_status()
        return response

    raise RuntimeError("Unexpected retry loop termination")


def fetch_pages(
    client: httpx.Client,
    query: str,
    max_pages: int,
    *,
    start_page: int = 1,
    start_token: str | None = None,
):
    token = start_token

    for page_number in range(start_page, max_pages + 1):
        payload = {
            "query": query,
            "fields": SEARCH_FIELDS,
            "limit": PAGE_SIZE,
            "scope": "ALL",
            "paginationMode": "ITERATION",
        }

        if token is not None:
            payload["iterationNextToken"] = token

        response = post_with_retry(client, payload)
        data = response.json()

        if not isinstance(data, dict):
            raise TypeError("Unexpected TED response")

        if data.get("timedOut") is True:
            raise RuntimeError("TED search timed out")

        notices = data.get("notices")

        if not isinstance(notices, list):
            raise TypeError("Invalid notices collection")

        next_token = data.get("iterationNextToken")

        yield (
            page_number,
            response.content,
            len(notices),
            data.get("totalNoticeCount"),
            next_token if notices else None,
        )

        if not notices or not next_token:
            break

        token = next_token


def atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def save_manifest(path: Path, manifest: dict) -> None:
    content = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    atomic_write(path, content)


def run_download(
    client: httpx.Client,
    run_dir: Path,
    *,
    max_pages: int,
    query: str | None = None,
) -> None:
    if max_pages < 1:
        raise ValueError("max_pages must be positive")

    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"

    if manifest_path.exists():
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

        if query is not None and query != manifest["query"]:
            raise ValueError("Query differs from existing run")

        if (
            manifest["page_size"] != PAGE_SIZE
            or manifest["fields"] != SEARCH_FIELDS
        ):
            raise ValueError("Incompatible ingestion configuration")

        if manifest["status"] == "completed":
            print("Run already completed.")
            return

        print("Resuming existing run.")

    else:
        if query is None:
            raise ValueError("Query required for a new run")

        manifest = {
            "query": query,
            "fields": SEARCH_FIELDS,
            "page_size": PAGE_SIZE,
            "pagination_mode": "ITERATION",
            "status": "partial",
            "next_token": None,
            "pages": [],
        }

        save_manifest(manifest_path, manifest)

    start_page = len(manifest["pages"]) + 1

    if start_page > max_pages:
        print("Page limit already reached.")
        return

    start_token = manifest["next_token"]

    if start_page > 1 and not start_token:
        raise RuntimeError("Missing checkpoint token")

    for page_number, content, count, total, next_token in fetch_pages(
        client,
        manifest["query"],
        max_pages,
        start_page=start_page,
        start_token=start_token,
    ):
        downloaded_before = sum(
            page["record_count"]
            for page in manifest["pages"]
        )

        if (
            not next_token
            and total is not None
            and downloaded_before + count < total
        ):
            raise RuntimeError(
                "Iteration ended before all notices were downloaded"
            )

        filename = f"page_{page_number:03d}.json"
        atomic_write(run_dir / filename, content)

        manifest["pages"].append(
            {
                "file": filename,
                "record_count": count,
                "fetched_at_utc": datetime.now(UTC).isoformat(),
            }
        )

        manifest["next_token"] = next_token
        manifest["status"] = (
            "completed"
            if count == 0 or not next_token
            else "partial"
        )

        save_manifest(manifest_path, manifest)

        print(f"Page {page_number}: {count} notices")
        print(f"Total downloaded: {downloaded_before + count}")

    print(f"Status: {manifest['status']}")
    print(f"Saved to: {run_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES)
    args = parser.parse_args()

    if args.resume is not None:
        run_dir = args.resume
        query = None
    else:
        since = datetime.now(UTC).date() - timedelta(days=45)
        query = build_query(since)

        run_id = datetime.now(UTC).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        run_dir = Path("data/raw") / f"ted_{run_id}"

    with httpx.Client(timeout=30.0) as client:
        run_download(
            client,
            run_dir,
            query=query,
            max_pages=args.max_pages,
        )


if __name__ == "__main__":
    main()
