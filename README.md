# TenderScope

[![CI](https://github.com/Mateusz0126/tenderscope/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Mateusz0126/tenderscope/actions/workflows/ci.yml)

TenderScope collects public procurement notices from the [TED Search API](https://ted.europa.eu/), checks their quality and prepares Parquet tables for analysis. The current scope is Polish buyers and IT-related CPV codes (`72*`).

The batch pipeline runs in Azure. Deployment and ETL are manual and require approval. A separate local history builder combines explicitly selected batches without counting retries twice.

## Data flow

```text
TED API -> Bronze JSON -> Silver Parquet -> quality checks -> run-level Gold
                              |                                |
                              +------ publish to ADLS ---------+
                                        |
                       reviewed catalog selects complete batches
                                        |
                       historical tables + aggregated Gold
                                        |
                              future Power BI model
```

Transformation and validation happen locally inside the job before publication. ADLS stores the results. The watermark advances only after successful publication. The history builder reads selected outputs; it never changes that watermark.

## What works

| Area | Implementation |
| --- | --- |
| Ingestion | Pagination, retries, saved checkpoints and local resume |
| Silver | Notice, notice–buyer-name and notice–CPV tables with explicit schemas |
| Quality | Source-shape checks, Silver schema checks and eight relational checks |
| Publication | Single-use run IDs, completion marker and conditional watermark writes |
| Gold | Daily, buyer-name, CPV and notice-type summaries; per-run HTML report |
| History | Reviewed selection, whole-window corrections, source run IDs and file hashes |
| Delivery | CI, Docker, Bicep, OIDC and separate deployment/execution identities |

The implementation uses Python, HTTPX, Polars, DuckDB and the Azure SDK. The dataset is currently small enough to process in one container; no distributed engine is needed.

## Verified examples

- The [11 November batch](https://github.com/Mateusz0126/tenderscope/actions/runs/43640055844) produced 16 notices and a Gold report in Azure.
- The [14 November batch](https://github.com/Mateusz0126/tenderscope/actions/runs/43833398567) returned zero notices and verified empty-day reporting, publication reservation and watermark advancement.
- The history builder combined the selected 12–14 November batches into **53 notices**: 27, 26 and zero per day. This was a local build from existing Azure outputs. The selection is recorded in [the example catalog](catalogs/dev-history.json).

These are bounded examples, not continuous or complete coverage of the procurement market.

## Run locally

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync --locked
uv run python -m tenderscope.pipeline --max-pages 2 --allow-partial
```

The default query looks back 45 days and fetches at most two pages of 50 notices. `--allow-partial` permits a sample; the report labels it accordingly. Without that flag, incomplete extraction fails before publication.

For a closed date window:

```powershell
uv run python -m tenderscope.pipeline `
  --since 2026-11-12 --until 2026-11-12 --max-pages 10
```

Local outputs go to `data/raw/<run_id>`, `data/silver/<run_id>` and `data/gold/<run_id>`. They are ignored by Git. To resume interrupted local ingestion, use `--resume data/raw/<run_id>` with a sufficient `--max-pages` limit. An already reserved cloud publication ID cannot be reused.

Cloud publication is enabled by `--storage-account` or `TENDERSCOPE_STORAGE_ACCOUNT`. Leave both unset for a local-only run. State-enforced cloud runs also use `--state-policy enforce`; see the deployment and recovery guides before running them.

## Build history

Follow [the history walkthrough](docs/history.md) to download only the catalog-selected inputs. Then build a new output directory:

```powershell
uv run python -m tenderscope.history `
  --catalog catalogs/dev-history.json `
  --source-root data/history-inputs/nov12-14 `
  --output data/history/nov12-14
```

The build rejects gaps, overlaps, partial batches and repeated notice IDs across accepted windows. Corrections replace an entire earlier window through an explicit catalog entry. Historical outputs include source run IDs and a complete calendar, so a day with no notices is distinguishable from missing coverage.

## Interpreting the results

A notice is a publication record, not necessarily a distinct procurement procedure. Buyer counts use names, not resolved organization IDs. One notice can have several CPV codes, so CPV counts are not additive across categories. A complete extraction means pagination finished at that time; later source corrections are still possible.

## Development

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

CI also builds the Docker image and compiles Bicep. Tests use local fixtures and simulated external services; actual Azure runs are separate supervised checks.

## Documentation

- [Architecture and identities](docs/architecture.md)
- [Module responsibilities and dependencies](docs/codebase.md)
- [Data contracts and metric definitions](docs/data-contracts.md)
- [Historical selection and corrections](docs/history.md)
- [Supervised backfill of earlier dates](docs/backfill.md)
- [State, failures and recovery](docs/state-and-recovery.md)
- [Deployment and manual ETL](docs/deployment.md)
- [Infrastructure and cost controls](infra/README.md)
- [Current status and remaining work](docs/project-status.md)
- [Demonstration checklist](docs/demo.md)

Power BI, automatic detection of historical corrections, proactive failure alerts and storage lifecycle policies remain open. Execution stays manual. The project is independent of TED and the European Commission.
