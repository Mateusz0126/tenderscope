
import json
from pathlib import Path

import duckdb


def validate_silver(
    run_dir: Path,
    *,
    allow_partial: bool = False,
) -> dict[str, int]:
    """Validate Silver data against the Bronze manifest."""

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    if manifest["status"] != "completed" and not allow_partial:
        raise RuntimeError("Bronze run is not completed")

    expected = sum(
        page["record_count"]
        for page in manifest["pages"]
    )

    silver_dir = Path("data/silver") / run_dir.name

    with duckdb.connect(":memory:") as con:
        for table in ("notice", "notice_cpv", "notice_buyer"):
            path = silver_dir / f"{table}.parquet"
            con.read_parquet(str(path)).create_view(table)

        total, unique_ids, invalid_ids, missing_dates = (
            con.execute("""
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT notice_id),
                    COUNT(*) FILTER (
                        WHERE notice_id IS NULL
                           OR TRIM(notice_id) = ''
                    ),
                    COUNT(*) FILTER (
                        WHERE publication_date IS NULL
                    )
                FROM notice
            """).fetchone()
        )

        checks = {
            "Bronze/Silver count": total == expected,
            "Unique IDs": total == unique_ids,
            "Valid IDs": invalid_ids == 0,
            "Publication dates": missing_dates == 0,
        }

        for table, column in (
            ("notice_cpv", "cpv_code"),
            ("notice_buyer", "buyer_name"),
        ):
            duplicates = con.execute(f"""
                SELECT COUNT(*)
                FROM (
                    SELECT notice_id, {column}
                    FROM {table}
                    GROUP BY notice_id, {column}
                    HAVING COUNT(*) > 1
                )
            """).fetchone()[0]

            orphans = con.execute(f"""
                SELECT COUNT(*)
                FROM {table} r
                LEFT JOIN notice n
                    ON r.notice_id = n.notice_id
                WHERE n.notice_id IS NULL
            """).fetchone()[0]

            checks[f"{table}: unique pairs"] = duplicates == 0
            checks[f"{table}: no orphans"] = orphans == 0

    print("\n=== SILVER QUALITY GATE ===")

    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")

    failed = [
        name for name, passed in checks.items()
        if not passed
    ]

    if failed:
        raise RuntimeError(
            f"Silver validation failed: {', '.join(failed)}"
        )

    return {
        "bronze_records": expected,
        "silver_records": total,
        "checks_passed": len(checks),
    }
