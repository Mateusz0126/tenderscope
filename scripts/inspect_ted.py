
import json
from pathlib import Path

FILE_PATH = Path("data/raw/ted_sample.json")


def main() -> None:
    with FILE_PATH.open(encoding="utf-8") as file:
        data = json.load(file)

    notices = data["notices"]

    print("\n=== RESPONSE METADATA ===")
    print("Root keys:", list(data.keys()))
    print("Number of notices:", len(notices))

    print("\n=== FIELD PROFILING ===")

    all_fields = sorted(
        {key for notice in notices for key in notice}
    )

    for field in all_fields:
        values = [notice.get(field) for notice in notices]

        types = sorted(
            {type(value).__name__ for value in values if value is not None}
        )

        missing = sum(value is None for value in values)

        sample = next(
            (value for value in values if value is not None),
            None,
        )

        if isinstance(sample, dict):
            preview = f"Object keys: {list(sample.keys())[:5]}"
        elif isinstance(sample, list):
            preview = f"List with {len(sample)} elements"
        else:
            preview = str(sample)[:100]

        print(f"\nField: {field}")
        print(f"  Types: {types}")
        print(f"  Missing: {missing}/{len(notices)}")
        print(f"  Sample: {preview}")


        print("\n=== NESTED STRUCTURES ===")

        for notice in notices[:3]:
            print("\n" + "=" * 50)
            print("Notice:", notice["publication-number"])

            for field in [
                "buyer-name",
                "buyer-country",
                "classification-cpv",
            ]:
                value = notice.get(field)

                print(f"\n{field}:")
                print(
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        indent=2,
                    )[:1000]
                )

            links = notice.get("links", {})

            print("\nAvailable link formats:")
            if isinstance(links, dict):
                for name, value in links.items():
                    print(f"  {name}: {str(value)[:200]}")

    print("\n=== DUPLICATE CHECK ===")
    ids = [notice.get("publication-number") for notice in notices]

    print("Records:", len(ids))
    print("Unique publication numbers:", len(set(ids)))


if __name__ == "__main__":
    main()
