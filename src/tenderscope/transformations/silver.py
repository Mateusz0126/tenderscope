
import json
from datetime import date
from pathlib import Path

import polars as pl


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
            name.strip()
            for name in names
            if isinstance(name, str) and name.strip()
        )
    )


def transform_notices(notices: list[dict]) -> tuple:
    notice_rows = []
    cpv_rows = []
    buyer_rows = []
    seen_ids = set()

    for notice in notices:
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


def main() -> None:
    source = Path("data/raw/ted_sample.json")
    target = Path("data/silver")

    with source.open(encoding="utf-8") as file:
        data = json.load(file)

    notices = data["notices"]

    notice_rows, cpv_rows, buyer_rows = transform_notices(notices)

    target.mkdir(parents=True, exist_ok=True)

    pl.DataFrame(notice_rows).write_parquet(
        target / "notice.parquet"
    )

    pl.DataFrame(cpv_rows).write_parquet(
        target / "notice_cpv.parquet"
    )

    pl.DataFrame(buyer_rows).write_parquet(
        target / "notice_buyer.parquet"
    )

    print("Silver transformation completed")
    print("Notices:", len(notice_rows))
    print("Notice-CPV relationships:", len(cpv_rows))
    print("Notice-buyer relationships:", len(buyer_rows))


if __name__ == "__main__":
    main()
