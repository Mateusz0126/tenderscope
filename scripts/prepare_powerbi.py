"""Create a local Power BI project bound to one verified history snapshot."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def prepare(snapshot: Path, output: Path, template: Path) -> Path:
    snapshot = snapshot.resolve()
    marker = json.loads((snapshot / "_SUCCESS.json").read_text(encoding="utf-8"))
    required = {
        "notice.parquet",
        "notice_buyer.parquet",
        "notice_cpv.parquet",
        "daily_summary.parquet",
    }
    hashes = marker["output_sha256"]
    if marker["schema_version"] != 1 or not required <= hashes.keys():
        raise ValueError("Expected a completed history snapshot with table hashes")
    for name in required:
        if hashlib.sha256((snapshot / name).read_bytes()).hexdigest() != hashes[name]:
            raise ValueError(f"Snapshot checksum mismatch: {name}")
    if output.exists():
        raise FileExistsError(f"Choose a new output directory: {output}")
    shutil.copytree(template, output)
    model_path = output / "TenderScope.SemanticModel" / "model.bim"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    parameter = next(
        x for x in model["model"]["expressions"] if x["name"] == "SourceFolder"
    )
    path_literal = snapshot.as_posix().replace('"', '""')
    parameter["expression"] = (
        f'"{path_literal}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'
    )
    model_path.write_text(
        json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output / "TenderScope.pbip"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    template = Path(__file__).resolve().parents[1] / "powerbi"
    print(prepare(args.snapshot, args.output, template).resolve())


if __name__ == "__main__":
    main()
