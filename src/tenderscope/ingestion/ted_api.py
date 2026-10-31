from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

TED_URL = "https://api.ted.europa.eu/v3/notices/search"

SEARCH_FIELDS = [
    "publication-number",
    "publication-date",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "notice-type",
]



def build_query(since: date) -> str:
    return (
        "buyer-country=POL "
        "AND classification-cpv=72* "
        f"AND publication-date>={since:%Y%m%d} "
        "SORT BY publication-date DESC"
    )


def main() -> None:
    since = datetime.now(UTC).date() - timedelta(days=45)

    payload = {
            "query": build_query(since),
            "fields": SEARCH_FIELDS,
            "page": 1,
            "limit": 10,
            "scope": "ALL",
            "paginationMode": "PAGE_NUMBER",
        }


    print("Query:", payload["query"])

    response = httpx.post(
        TED_URL,
        json=payload,
        timeout=30.0,
    )

    if response.is_error:
        print("API error:", response.text[:2000])
    response.raise_for_status()

    data = response.json()
    notices = data.get("notices")

    if not isinstance(notices, list):
        raise TypeError("Unexpected API response format")

    output = Path("data/raw/ted_sample.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(response.content)

    print("Total matching:", data.get("totalNoticeCount"))
    print("Downloaded:", len(notices))
    print("Saved to:", output)

    for notice in notices:
        print(
            notice.get("publication-number"),
            notice.get("publication-date"),
        )

    if notices:
        first_notice = notices[0]
        titles = first_notice.get("notice-title", {})

        print("\nAvailable fields:")
        print(sorted(first_notice.keys()))

        if isinstance(titles, dict):
            title_pl = titles.get("pol") or titles.get("eng")
        else:
            title_pl = titles

        print("\nFirst notice:")
        print("ID:", first_notice.get("publication-number"))
        print("Title:", title_pl)
        print("Date:", first_notice.get("publication-date"))


if __name__ == "__main__":
    main()
