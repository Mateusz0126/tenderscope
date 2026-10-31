
import json
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


def fetch_pages(
    client: httpx.Client,
    query: str,
    max_pages: int,
):
    token = None

    for page_number in range(1, max_pages + 1):
        payload = {
            "query": query,
            "fields": SEARCH_FIELDS,
            "limit": PAGE_SIZE,
            "scope": "ALL",
            "paginationMode": "ITERATION",
        }

        if token is not None:
            payload["iterationNextToken"] = token

        response = client.post(TED_URL, json=payload)
        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise TypeError("Unexpected TED response")

        if data.get("timedOut") is True:
            raise RuntimeError("TED search timed out")

        notices = data.get("notices")

        if not isinstance(notices, list):
            raise TypeError("Invalid notices collection")

        if not notices:
            print("No more notices.")
            break

        yield (
            page_number,
            response.content,
            len(notices),
            data.get("totalNoticeCount"),
        )

        token = data.get("iterationNextToken")

        if not token:
            break


def main() -> None:
    since = datetime.now(UTC).date() - timedelta(days=45)
    query = build_query(since)

    run_id = datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    output_dir = Path("data/raw") / f"ted_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": run_id,
        "query": query,
        "page_size": PAGE_SIZE,
        "pagination_mode": "ITERATION",
        "pages": [],
    }

    total_downloaded = 0

    with httpx.Client(timeout=30.0) as client:
        for page_number, content, count, total in fetch_pages(
            client,
            query,
            MAX_PAGES,
        ):
            filename = f"page_{page_number:03d}.json"

            (output_dir / filename).write_bytes(content)

            manifest["pages"].append(
                {
                    "file": filename,
                    "record_count": count,
                    "fetched_at_utc": datetime.now(
                        UTC
                    ).isoformat(),
                }
            )

            total_downloaded += count

            print(
                f"Page {page_number}: {count} records"
            )
            print(f"Total matching: {total}")

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nDownloaded: {total_downloaded}")
    print(f"Saved to: {output_dir}")


if __name__ == "__main__":
    main()
