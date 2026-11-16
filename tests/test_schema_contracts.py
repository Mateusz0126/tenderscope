import json

import polars as pl
import pytest

from tenderscope.quality.silver import validate_silver
from tenderscope.transformations.bronze_reader import load_bronze_run
from tenderscope.transformations.silver import BUYER_SCHEMA, CPV_SCHEMA, NOTICE_SCHEMA


@pytest.mark.parametrize("change", ["missing", "type", "extra"])
def test_silver_incompatible_schema_blocks_quality(tmp_path, monkeypatch, change):
    monkeypatch.chdir(tmp_path)
    raw = tmp_path / "data/raw/ted_schema"
    silver = tmp_path / "data/silver/ted_schema"
    raw.mkdir(parents=True)
    silver.mkdir(parents=True)
    (raw / "manifest.json").write_text(json.dumps({"status": "completed", "pages": []}))
    for name, schema in (
        ("notice", NOTICE_SCHEMA),
        ("notice_buyer", BUYER_SCHEMA),
        ("notice_cpv", CPV_SCHEMA),
    ):
        schema = dict(schema)
        if name == "notice":
            if change == "missing":
                del schema["notice_id"]
            elif change == "type":
                schema["publication_date"] = pl.String
            else:
                schema["unreviewed_field"] = pl.String
        pl.DataFrame(schema=schema).write_parquet(silver / f"{name}.parquet")
    with pytest.raises(ValueError, match="Silver schema v1 mismatch"):
        validate_silver(raw)


def test_unknown_bronze_contract_rejected(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"schema_version": 2}))
    with pytest.raises(ValueError, match="Unsupported Bronze"):
        load_bronze_run(tmp_path)
