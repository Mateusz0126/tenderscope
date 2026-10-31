
import json
from pathlib import Path


def load_bronze_run(
    run_dir: Path,
    *,
    allow_partial: bool = False,
) -> list[dict]:
    manifest_path = run_dir / "manifest.json"

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    status = manifest.get("status")

    if status != "completed" and not allow_partial:
        raise ValueError(
            f"Cannot process run with status: {status}"
        )

    pages = manifest.get("pages")

    if not isinstance(pages, list) or not pages:
        raise ValueError("No pages found in manifest")

    all_notices = []

    for page_number, page in enumerate(pages, start=1):
        expected_name = f"page_{page_number:03d}.json"

        if page.get("file") != expected_name:
            raise ValueError(
                f"Unexpected page sequence: {page.get('file')}"
            )

        page_path = run_dir / expected_name

        data = json.loads(
            page_path.read_text(encoding="utf-8")
        )

        if data.get("timedOut") is True:
            raise ValueError(
                f"TED timeout recorded in {expected_name}"
            )

        notices = data.get("notices")

        if not isinstance(notices, list):
            raise TypeError(
                f"Invalid notices in {expected_name}"
            )

        if not all(isinstance(item, dict) for item in notices):
            raise TypeError(
                f"Invalid notice record in {expected_name}"
            )

        if len(notices) != page["record_count"]:
            raise ValueError(
                f"Record count mismatch in {expected_name}"
            )

        all_notices.extend(notices)

    return all_notices
