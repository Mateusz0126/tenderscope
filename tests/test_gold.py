from datetime import date

import polars as pl

from tenderscope.transformations.gold import build_gold, write_gold


def test_build_gold_creates_run_level_kpis():
    notices = pl.DataFrame(
        {
            "notice_id": ["001", "002", "003"],
            "publication_date": [
                date(2026, 11, 12),
                date(2026, 11, 12),
                date(2026, 11, 13),
            ],
            "notice_type": ["competition", "competition", None],
        }
    )
    buyers = pl.DataFrame(
        {
            "notice_id": ["001", "002", "003"],
            "buyer_name": ["Buyer A", "Buyer A", "Buyer B"],
        }
    )
    cpvs = pl.DataFrame(
        {
            "notice_id": ["001", "002", "003", "003"],
            "cpv_code": ["72000000", "72000000", "72200000", "72300000"],
        }
    )

    models = build_gold(notices, buyers, cpvs)

    assert models["daily_summary"].to_dicts() == [
        {
            "publication_date": date(2026, 11, 12),
            "notice_count": 2,
            "unique_buyers": 1,
            "unique_cpv_codes": 1,
        },
        {
            "publication_date": date(2026, 11, 13),
            "notice_count": 1,
            "unique_buyers": 1,
            "unique_cpv_codes": 2,
        },
    ]
    assert models["buyer_summary"][0, "buyer_name"] == "Buyer A"
    assert models["buyer_summary"][0, "notice_count"] == 2
    assert models["notice_type_summary"].to_dicts() == [
        {"notice_type": "competition", "notice_count": 2},
        {"notice_type": "unknown", "notice_count": 1},
    ]


def test_write_gold_writes_typed_empty_models_and_report(tmp_path):
    silver_dir = tmp_path / "data/silver/ted_empty"
    target = tmp_path / "data/gold/ted_empty"
    silver_dir.mkdir(parents=True)

    pl.DataFrame(
        schema={
            "notice_id": pl.String,
            "publication_date": pl.Date,
            "notice_type": pl.String,
        }
    ).write_parquet(silver_dir / "notice.parquet")
    pl.DataFrame(
        schema={"notice_id": pl.String, "buyer_name": pl.String}
    ).write_parquet(silver_dir / "notice_buyer.parquet")
    pl.DataFrame(
        schema={"notice_id": pl.String, "cpv_code": pl.String}
    ).write_parquet(silver_dir / "notice_cpv.parquet")

    metrics = write_gold(silver_dir, target)

    assert metrics == {
        "notices": 0,
        "unique_buyers": 0,
        "unique_cpv_codes": 0,
        "notice_types": 0,
        "files": 6,
    }
    assert pl.read_parquet(target / "daily_summary.parquet").schema == {
        "publication_date": pl.Date,
        "notice_count": pl.UInt32,
        "unique_buyers": pl.UInt32,
        "unique_cpv_codes": pl.UInt32,
    }
    assert "No records in this run" in (
        target / "report.html"
    ).read_text(encoding="utf-8")

