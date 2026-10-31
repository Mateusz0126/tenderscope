
import json
from pathlib import Path


def main() -> None:
    runs = sorted(Path("data/raw").glob("ted_*/manifest.json"))

    if not runs:
        raise FileNotFoundError("No ingestion manifests found")

    manifest_path = runs[-1]
    run_dir = manifest_path.parent

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    all_ids = []

    for page in manifest["pages"]:
        file_path = run_dir / page["file"]

        data = json.loads(
            file_path.read_text(encoding="utf-8")
        )

        if data.get("timedOut"):
            raise RuntimeError(f"TED timeout: {file_path.name}")

        notices = data["notices"]

        assert len(notices) == page["record_count"]

        ids = [
            notice["publication-number"]
            for notice in notices
        ]

        all_ids.extend(ids)

        print(f"{file_path.name}: {len(ids)} notices")

    total = len(all_ids)
    unique = len(set(all_ids))
    duplicates = total - unique

    print("\n=== BRONZE VALIDATION ===")
    print("Run:", run_dir.name)
    print("Total records:", total)
    print("Unique notices:", unique)
    print("Duplicates:", duplicates)

    assert total > 0, "No records downloaded"
    assert duplicates == 0, "Duplicate notices detected"

    print("Bronze validation passed!")


if __name__ == "__main__":
    main()
