import argparse
from datetime import date
from pathlib import Path

import polars as pl

from tenderscope.transformations.bronze_reader import load_bronze_run

NOTICE_SCHEMA = {
    "notice_id": pl.String,
    "publication_date": pl.Date,
    "publication_date_raw": pl.String,
    "title_pl": pl.String,
    "title_en": pl.String,
    "notice_type": pl.String,
    "xml_url": pl.String,
}
CPV_SCHEMA = {
    "notice_id": pl.String,
    "cpv_code": pl.String,
}
SILVER_SCHEMA_VERSION = 1

BUYER_SCHEMA = {
    "notice_id": pl.String,
    "buyer_name": pl.String,
}


def validate_source_notice(notice: dict) -> None:
    """Contract v1: accept additive TED fields, reject incompatible known fields."""
    for field in ("notice-title", "buyer-name", "links"):
        value = notice.get(field)
        if value is not None and not isinstance(value, dict):
            raise TypeError(f"Invalid {field}: expected an object or null")
    for value in (notice.get("notice-title") or {}).values():
        if value is not None and not isinstance(value, str):
            raise TypeError("Invalid notice-title translation")
    for value in (notice.get("buyer-name") or {}).values():
        if not isinstance(value, list) or not all(
            isinstance(name, str) for name in value
        ):
            raise TypeError(
                "Invalid buyer-name translation: expected a list of strings"
            )
    links = notice.get("links") or {}
    xml = links.get("xml")
    if xml is not None and not isinstance(xml, dict):
        raise TypeError("Invalid links.xml: expected an object or null")
    if (
        isinstance(xml, dict)
        and xml.get("MUL") is not None
        and not isinstance(xml["MUL"], str)
    ):
        raise TypeError("Invalid links.xml.MUL")
    kind = notice.get("notice-type")
    if kind is not None and not isinstance(kind, str):
        raise TypeError("Invalid notice-type")
    codes = notice.get("classification-cpv")
    if codes is not None and (
        not isinstance(codes, list)
        or not all(
            isinstance(code, str)
            and len(code) == 8
            and code.isascii()
            and code.isdecimal()
            for code in codes
        )
    ):
        raise TypeError("Invalid classification-cpv: expected eight-digit strings")


def extract_buyers(raw: object) -> list[str]:
    """Extract unique buyer names, preferring Polish."""
    if not isinstance(raw, dict):
        return []

    names = raw.get("pol") or raw.get("eng")

    if not isinstance(names, list):
        names = next(
            (value for value in raw.values() if isinstance(value, list)),
            [],
        )

    return list(
        dict.fromkeys(
            name.strip() for name in names if isinstance(name, str) and name.strip()
        )
    )


def transform_notices(notices: list[dict]) -> tuple:
    notice_rows = []
    cpv_rows = []
    buyer_rows = []
    seen_ids = set()

    for notice in notices:
        validate_source_notice(notice)
        notice_id = notice.get("publication-number")

        if not isinstance(notice_id, str) or not notice_id:
            raise ValueError("Missing publication number")

        if notice_id in seen_ids:
            raise ValueError(f"Duplicate notice: {notice_id}")

        seen_ids.add(notice_id)

        raw_date = notice.get("publication-date")

        if not isinstance(raw_date, str):
            raise TypeError("Invalid publication date type")

        publication_date = date.fromisoformat(raw_date[:10])

        titles = notice.get("notice-title") or {}

        if not isinstance(titles, dict):
            raise TypeError("Invalid notice title type")

        links = notice.get("links") or {}
        xml_links = links.get("xml") or {}

        notice_rows.append(
            {
                "notice_id": notice_id,
                "publication_date": publication_date,
                "publication_date_raw": raw_date,
                "title_pl": titles.get("pol"),
                "title_en": titles.get("eng"),
                "notice_type": notice.get("notice-type"),
                "xml_url": xml_links.get("MUL"),
            }
        )

        cpv_codes = notice.get("classification-cpv") or []

        if not isinstance(cpv_codes, list):
            raise TypeError("Invalid CPV field type")

        for code in sorted(set(cpv_codes)):
            cpv_rows.append(
                {
                    "notice_id": notice_id,
                    "cpv_code": code,
                }
            )

        for buyer in extract_buyers(notice.get("buyer-name")):
            buyer_rows.append(
                {
                    "notice_id": notice_id,
                    "buyer_name": buyer,
                }
            )

    return notice_rows, cpv_rows, buyer_rows


def write_silver(
    run_dir: Path,
    *,
    allow_partial: bool = False,
) -> dict[str, int]:
    notices = load_bronze_run(
        run_dir,
        allow_partial=allow_partial,
    )

    notice_rows, cpv_rows, buyer_rows = transform_notices(notices)

    target = Path("data/silver") / run_dir.name
    target.mkdir(parents=True, exist_ok=True)

    pl.DataFrame(notice_rows, schema=NOTICE_SCHEMA).write_parquet(
        target / "notice.parquet"
    )
    pl.DataFrame(cpv_rows, schema=CPV_SCHEMA).write_parquet(
        target / "notice_cpv.parquet"
    )
    pl.DataFrame(buyer_rows, schema=BUYER_SCHEMA).write_parquet(
        target / "notice_buyer.parquet"
    )

    return {
        "notices": len(notice_rows),
        "cpv_relationships": len(cpv_rows),
        "buyer_relationships": len(buyer_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    metrics = write_silver(
        args.run_dir,
        allow_partial=args.allow_partial,
    )

    print("\n=== SILVER TRANSFORMATION ===")
    print("Run:", args.run_dir.name)

    for name, value in metrics.items():
        print(f"{name}: {value}")


if __name__ == "__main__":
    main()
