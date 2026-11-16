"""Preparation must not silently load modified data or overwrite an edited report."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_powerbi.py"
spec = importlib.util.spec_from_file_location("prepare_powerbi", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def snapshot(tmp_path):
    root = tmp_path / "history"
    root.mkdir()
    hashes = {}
    for name in ("notice", "notice_buyer", "notice_cpv", "daily_summary"):
        path = root / f"{name}.parquet"
        path.write_bytes(b"fixture")
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "_SUCCESS.json").write_text(
        json.dumps({"schema_version": 1, "output_sha256": hashes}), encoding="utf-8"
    )
    return root


def test_prepare_preserves_template_and_refuses_overwrite(tmp_path):
    root = snapshot(tmp_path)
    template = SCRIPT.parents[1] / "powerbi"
    model_path = template / "TenderScope.SemanticModel" / "model.bim"
    original = model_path.read_bytes()
    output = tmp_path / "report"
    assert module.prepare(root, output, template).is_file()
    model = json.loads(
        (output / "TenderScope.SemanticModel" / "model.bim").read_text(encoding="utf-8")
    )
    assert root.as_posix() in model["model"]["expressions"][0]["expression"]
    assert model_path.read_bytes() == original
    with pytest.raises(FileExistsError):
        module.prepare(root, output, template)


@pytest.mark.parametrize("failure", ["changed", "missing_hash", "no_marker"])
def test_prepare_rejects_unverified_snapshot(tmp_path, failure):
    root = snapshot(tmp_path)
    marker = root / "_SUCCESS.json"
    if failure == "changed":
        (root / "notice.parquet").write_bytes(b"changed")
    elif failure == "missing_hash":
        marker.write_text(
            '{"schema_version": 1, "output_sha256": {}}', encoding="utf-8"
        )
    else:
        marker.unlink()
    output = tmp_path / "report"
    with pytest.raises((ValueError, FileNotFoundError)):
        module.prepare(root, output, SCRIPT.parents[1] / "powerbi")
    assert not output.exists()
