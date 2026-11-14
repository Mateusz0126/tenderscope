import html
import json
from datetime import date
from pathlib import Path

import polars as pl

DAILY_SCHEMA = {
    "publication_date": pl.Date,
    "notice_count": pl.UInt32,
    "unique_buyers": pl.UInt32,
    "unique_cpv_codes": pl.UInt32,
}
BUYER_SUMMARY_SCHEMA = {
    "buyer_name": pl.String,
    "notice_count": pl.UInt32,
    "first_publication_date": pl.Date,
    "last_publication_date": pl.Date,
}
CPV_SUMMARY_SCHEMA = {
    "cpv_code": pl.String,
    "notice_count": pl.UInt32,
}
NOTICE_TYPE_SUMMARY_SCHEMA = {
    "notice_type": pl.String,
    "notice_count": pl.UInt32,
}


def _empty(schema: dict[str, pl.DataType]) -> pl.DataFrame:
    return pl.DataFrame(schema=schema)


def build_gold(
    notices: pl.DataFrame,
    buyers: pl.DataFrame,
    cpvs: pl.DataFrame,
) -> dict[str, pl.DataFrame]:
    if notices.is_empty():
        return {
            "daily_summary": _empty(DAILY_SCHEMA),
            "buyer_summary": _empty(BUYER_SUMMARY_SCHEMA),
            "cpv_summary": _empty(CPV_SUMMARY_SCHEMA),
            "notice_type_summary": _empty(NOTICE_TYPE_SUMMARY_SCHEMA),
        }

    notice_dates = notices.select("notice_id", "publication_date")

    daily = notices.group_by("publication_date").agg(
        pl.len().cast(pl.UInt32).alias("notice_count")
    )

    if buyers.is_empty():
        buyers_by_day = pl.DataFrame(
            {
                "publication_date": pl.Series([], dtype=pl.Date),
                "unique_buyers": pl.Series([], dtype=pl.UInt32),
            }
        )
        buyer_summary = _empty(BUYER_SUMMARY_SCHEMA)
    else:
        buyers_with_dates = buyers.join(
            notice_dates,
            on="notice_id",
            how="inner",
        )
        buyers_by_day = buyers_with_dates.group_by(
            "publication_date"
        ).agg(
            pl.col("buyer_name")
            .n_unique()
            .cast(pl.UInt32)
            .alias("unique_buyers")
        )
        buyer_summary = (
            buyers_with_dates.group_by("buyer_name")
            .agg(
                pl.col("notice_id")
                .n_unique()
                .cast(pl.UInt32)
                .alias("notice_count"),
                pl.col("publication_date").min().alias(
                    "first_publication_date"
                ),
                pl.col("publication_date").max().alias(
                    "last_publication_date"
                ),
            )
            .sort(
                ["notice_count", "buyer_name"],
                descending=[True, False],
            )
        )

    if cpvs.is_empty():
        cpvs_by_day = pl.DataFrame(
            {
                "publication_date": pl.Series([], dtype=pl.Date),
                "unique_cpv_codes": pl.Series([], dtype=pl.UInt32),
            }
        )
        cpv_summary = _empty(CPV_SUMMARY_SCHEMA)
    else:
        cpvs_with_dates = cpvs.join(
            notice_dates,
            on="notice_id",
            how="inner",
        )
        cpvs_by_day = cpvs_with_dates.group_by("publication_date").agg(
            pl.col("cpv_code")
            .n_unique()
            .cast(pl.UInt32)
            .alias("unique_cpv_codes")
        )
        cpv_summary = (
            cpvs_with_dates.group_by("cpv_code")
            .agg(
                pl.col("notice_id")
                .n_unique()
                .cast(pl.UInt32)
                .alias("notice_count")
            )
            .sort(
                ["notice_count", "cpv_code"],
                descending=[True, False],
            )
        )

    daily = (
        daily.join(buyers_by_day, on="publication_date", how="left")
        .join(cpvs_by_day, on="publication_date", how="left")
        .with_columns(
            pl.col("unique_buyers").fill_null(0),
            pl.col("unique_cpv_codes").fill_null(0),
        )
        .select(*DAILY_SCHEMA)
        .sort("publication_date")
    )

    notice_type_summary = (
        notices.with_columns(
            pl.col("notice_type")
            .fill_null("unknown")
            .replace("", "unknown")
        )
        .group_by("notice_type")
        .agg(pl.len().cast(pl.UInt32).alias("notice_count"))
        .sort(
            ["notice_count", "notice_type"],
            descending=[True, False],
        )
    )

    return {
        "daily_summary": daily,
        "buyer_summary": buyer_summary.select(*BUYER_SUMMARY_SCHEMA),
        "cpv_summary": cpv_summary.select(*CPV_SUMMARY_SCHEMA),
        "notice_type_summary": notice_type_summary.select(
            *NOTICE_TYPE_SUMMARY_SCHEMA
        ),
    }


def _json_rows(frame: pl.DataFrame) -> list[dict[str, object]]:
    rows = frame.to_dicts()

    for row in rows:
        for key, value in row.items():
            if isinstance(value, date):
                row[key] = value.isoformat()

    return rows


def _table_rows(
    rows: list[dict[str, object]],
    columns: tuple[tuple[str, str], ...],
) -> str:
    if not rows:
        return '<tr><td colspan="4">No records in this run.</td></tr>'

    return "".join(
        "<tr>"
        + "".join(
            f"<td>{html.escape(str(row.get(key, '')))}</td>"
            for key, _ in columns
        )
        + "</tr>"
        for row in rows
    )


def render_report(summary: dict[str, object]) -> str:
    totals = summary["totals"]
    date_range = summary["date_range"]

    sections = (
        (
            "Top buyers",
            summary["top_buyers"],
            (("buyer_name", "Buyer"), ("notice_count", "Notices")),
        ),
        (
            "Top CPV codes",
            summary["top_cpv_codes"],
            (("cpv_code", "CPV code"), ("notice_count", "Notices")),
        ),
        (
            "Notice types",
            summary["notice_types"],
            (("notice_type", "Type"), ("notice_count", "Notices")),
        ),
    )

    tables = "".join(
        f"""
        <section class="panel">
          <h2>{html.escape(title)}</h2>
          <table>
            <thead><tr>{''.join(f'<th>{html.escape(label)}</th>' for _, label in columns)}</tr></thead>
            <tbody>{_table_rows(rows, columns)}</tbody>
          </table>
        </section>
        """
        for title, rows, columns in sections
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TenderScope run report</title>
  <style>
    :root {{ color-scheme: dark; --bg: #0b1220; --panel: #111c30; --muted: #9fb0c9; --accent: #5eead4; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: var(--bg); color: #edf4ff; }}
    main {{ width: min(1100px, 92vw); margin: 0 auto; padding: 48px 0 64px; }}
    header {{ margin-bottom: 28px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(2rem, 5vw, 3.4rem); }}
    h2 {{ margin-top: 0; font-size: 1.1rem; }}
    p {{ color: var(--muted); }}
    .cards, .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
    .card, .panel {{ background: var(--panel); border: 1px solid #223454; border-radius: 14px; padding: 20px; }}
    .card strong {{ display: block; color: var(--accent); font-size: 2rem; margin-top: 6px; }}
    .grid {{ margin-top: 16px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; text-align: left; border-bottom: 1px solid #223454; }}
    th {{ color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; }}
    footer {{ margin-top: 24px; color: var(--muted); font-size: .9rem; }}
  </style>
</head>
<body>
  <main>
    <header>
      <p>TenderScope · validated run</p>
      <h1>Polish IT procurement snapshot</h1>
      <p>Run {html.escape(str(summary['run_id']))} · {html.escape(str(date_range['from']))} to {html.escape(str(date_range['to']))}</p>
    </header>
    <section class="cards">
      <div class="card">Notices<strong>{totals['notices']}</strong></div>
      <div class="card">Unique buyers<strong>{totals['unique_buyers']}</strong></div>
      <div class="card">Unique CPV codes<strong>{totals['unique_cpv_codes']}</strong></div>
      <div class="card">Notice types<strong>{totals['notice_types']}</strong></div>
    </section>
    <div class="grid">{tables}</div>
    <footer>Generated from quality-gated Silver Parquet data. Counts are scoped to this run.</footer>
  </main>
</body>
</html>
"""


def write_gold(
    silver_dir: Path,
    target_dir: Path | None = None,
) -> dict[str, object]:
    target = target_dir or Path("data/gold") / silver_dir.name
    target.mkdir(parents=True, exist_ok=True)

    models = build_gold(
        pl.read_parquet(silver_dir / "notice.parquet"),
        pl.read_parquet(silver_dir / "notice_buyer.parquet"),
        pl.read_parquet(silver_dir / "notice_cpv.parquet"),
    )

    for name, frame in models.items():
        frame.write_parquet(target / f"{name}.parquet")

    daily_rows = _json_rows(models["daily_summary"])
    summary = {
        "run_id": silver_dir.name,
        "date_range": {
            "from": daily_rows[0]["publication_date"] if daily_rows else None,
            "to": daily_rows[-1]["publication_date"] if daily_rows else None,
        },
        "totals": {
            "notices": int(models["daily_summary"]["notice_count"].sum()),
            "unique_buyers": models["buyer_summary"].height,
            "unique_cpv_codes": models["cpv_summary"].height,
            "notice_types": models["notice_type_summary"].height,
        },
        "top_buyers": _json_rows(models["buyer_summary"].head(10)),
        "top_cpv_codes": _json_rows(models["cpv_summary"].head(10)),
        "notice_types": _json_rows(models["notice_type_summary"]),
        "daily": daily_rows,
    }

    (target / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (target / "report.html").write_text(
        render_report(summary),
        encoding="utf-8",
    )

    return {
        **summary["totals"],
        "files": len(models) + 2,
    }

