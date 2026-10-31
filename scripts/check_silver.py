
import argparse
from pathlib import Path

from tenderscope.quality.silver import validate_silver


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--allow-partial", action="store_true")

    args = parser.parse_args()

    metrics = validate_silver(
        args.run_dir,
        allow_partial=args.allow_partial,
    )

    print("\n=== VALIDATION METRICS ===")

    for name, value in metrics.items():
        print(f"{name}: {value}")


if __name__ == "__main__":
    main()
