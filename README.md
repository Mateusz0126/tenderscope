# TenderScope

[![CI](https://github.com/Mateusz0126/tenderscope/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Mateusz0126/tenderscope/actions/workflows/ci.yml)

**An end-to-end Data Engineering project for exploring European public procurement notices.**

TenderScope ingests public tender notices from the [Tenders Electronic Daily (TED)](https://ted.europa.eu/) Search API, preserves raw responses in a Bronze layer, transforms them into analytical Parquet datasets in a Silver layer, validates data quality with DuckDB, and builds run-level Gold procurement KPIs with a self-contained HTML report.

> **Status:** working portfolio data platform. The complete Bronze → Silver → Gold path has been verified in Azure. Deployments and data runs are manual and approval-gated. See the [current status and maturity assessment](docs/project-status.md).

## What this project demonstrates

| Capability | Implementation |
| --- | --- |
| Resilient ingestion | TED pagination, retry/backoff, atomic checkpoints and resume |
| Analytical modeling | Normalized Parquet datasets and run-level procurement KPIs |
| Data quality | Eight DuckDB checks block invalid publication |
| Cloud engineering | ADLS Gen2, ACR and Container Apps Jobs defined with Bicep |
| Secure delivery | GitHub Actions OIDC, separate managed identities and scoped roles |
| Operational control | Manual date windows, protected `dev` approvals and immutable image digests |
| Durable orchestration | Versioned watermark, contiguous windows and ETag conflict protection |
| Cost awareness | Consumption execution, no scheduler, no hosted dashboard and bounded runs |

## Project documentation

- [Architecture and trust boundaries](docs/architecture.md)
- [Codebase structure and dependency rationale](docs/codebase.md)
- [Durable state, failure modes and recovery](docs/state-and-recovery.md)
- [Data contracts, metric definitions and historical corrections](docs/data-contracts.md)
- [Five-to-seven minute demonstration](docs/demo.md)
- [Current status, evidence, gaps and maturity](docs/project-status.md)
- [Supervised deployment and ETL execution](docs/deployment.md)
- [Azure infrastructure and cost posture](infra/README.md)

## Architecture

```text
TED Search API (REST / JSON)
         |
         | HTTPX: iterative pagination, retries, checkpoint/resume
         v
Bronze (raw JSON files + manifest.json)
         |
         | Python + Polars
         v
Silver (Parquet)
  ├── notice.parquet
  ├── notice_cpv.parquet
  └── notice_buyer.parquet
         |
         | DuckDB quality gate (8 checks)
         v
Validated Silver datasets
         |
         | Polars aggregations
         v
Gold (run-level KPIs + static HTML report)
         |
         | publish only after the quality gate passes
         v
Azure Data Lake Storage Gen2
  ├── bronze/runs/<run_id>/
  ├── silver/runs/<run_id>/
  │   └── _SUCCESS.json
  ├── gold/runs/<run_id>/
  └── control/state/ted-poland-it.json
             └── versioned watermark + ETag
```

The pipeline always writes and validates local working files first. When `TENDERSCOPE_STORAGE_ACCOUNT` is configured, it then uploads Bronze, Silver and Gold files to ADLS Gen2. The Silver `_SUCCESS.json` marker is written after every layer has been uploaded. In state-enforced mode, the watermark is advanced last with an ETag precondition, so consumers can distinguish complete runs and concurrent writers cannot silently overwrite progress.

The complete component and identity flow is documented in [Architecture and trust boundaries](docs/architecture.md).

## Tech stack

| Area | Technology |
| --- | --- |
| Language and packaging | Python 3.12+, uv |
| Data source | TED Search API v3 |
| API client | HTTPX |
| Data transformation | Polars |
| Storage format | JSON (Bronze), Parquet (Silver) |
| Analytical output | Parquet + JSON + self-contained HTML (Gold) |
| Data quality | DuckDB |
| Cloud storage | Azure Data Lake Storage Gen2, Azure Identity |
| Containerization | Docker |
| Testing and linting | pytest, Ruff, GitHub Actions |

## Current data scope

The default query selects notices where:

- Buyer country is **Poland** (`POL`).
- CPV classification matches **`72*`** (IT and related services).
- Publication date is within the **last 45 days**.
- Results are sorted by publication date, newest first.

The query is built in `src/tenderscope/ingestion/ted_api.py`. The ingestion code uses TED's iteration-based pagination with a page size of **50 notices**. By default, it searches the last **45 days** and processes at most **2 pages**, so a default run is a bounded sample, **not necessarily a complete extract** of all matching notices.

## Verified cloud run

On **2026-11-14**, the protected workflow processed the completed historical day **2026-11-11** after an explicit `dev` approval. The run published all three layers and produced:

- 16 notices;
- 13 distinct buyer names;
- 39 unique CPV codes;
- 3 notice types;
- 3 Silver Parquet datasets, 4 Gold Parquet summaries, `summary.json` and `report.html`.

Evidence: [successful ETL workflow](https://github.com/Mateusz0126/tenderscope/actions/runs/43640055844) and [Gold implementation PR](https://github.com/Mateusz0126/tenderscope/pull/11). The batch is evidence that the bounded workflow works end to end; it is not a claim that the project continuously processes every TED notice.

## Repository structure

```text
.
├── src/tenderscope/
│   ├── ingestion/
│   │   ├── ted_api.py          # TED endpoint, fields and query
│   │   └── ted_pages.py        # Pagination, retry, checkpoints and manifests
│   ├── transformations/
│   │   ├── bronze_reader.py    # Read and validate raw page files
│   │   ├── silver.py           # Normalize notices and write Parquet
│   │   └── gold.py             # Build KPIs and the static report
│   ├── quality/
│   │   └── silver.py           # DuckDB data-quality gate
│   ├── storage/
│   │   └── adls.py             # Reserved Bronze/Silver/Gold publication
│   └── pipeline.py             # End-to-end orchestration
├── scripts/
│   └── smoke_adls.py           # Standalone ADLS connectivity smoke test
├── docs/
│   ├── architecture.md         # Components, identities and failure semantics
│   ├── demo.md                 # Short portfolio walkthrough
│   ├── project-status.md       # Evidence, gaps and maturity assessment
│   └── deployment.md           # Supervised OIDC deployment and execution
├── infra/                      # Reproducible Azure Bicep templates
├── Dockerfile
├── .dockerignore
├── pyproject.toml
└── README.md
```

Local runtime output is stored under `data/raw/`, `data/silver/` and `data/gold/`, all ignored by Git.

## Quick start

### Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

### Install dependencies

```bash
uv sync
```

### Run the pipeline

```bash
uv run python -m tenderscope.pipeline --max-pages 2 --allow-partial
```

For a controlled incremental batch, provide an inclusive publication-date window:

```bash
uv run python -m tenderscope.pipeline \
  --since 2026-11-02 \
  --until 2026-11-02 \
  --max-pages 2
```

The pipeline rejects reversed windows and records the exact query in the Bronze manifest. Date bounds cannot be changed while resuming an existing run, which prevents a checkpoint from silently switching to a different data scope.

Do not use `--allow-partial` for a batch that will advance a future watermark. If the daily window exceeds the page limit, increase `--max-pages` or resume the same run so the window becomes complete before publication.

A completed window with zero matching notices is a valid run. TenderScope writes typed, empty Silver Parquet files and still executes all quality checks, so an empty day does not break future incremental processing.

To publish a validated run to ADLS Gen2, set the storage account name before starting the same command:

```powershell
$env:TENDERSCOPE_STORAGE_ACCOUNT = "<storage-account-name>"
uv run python -m tenderscope.pipeline --max-pages 2 --allow-partial
```

In Azure Container Apps, `DefaultAzureCredential` uses the job's user-assigned managed identity selected through `AZURE_CLIENT_ID`. No storage key or connection string is required.

For a state-enforced cloud batch, add `--state-policy enforce`. The first run for a new stream requires `--since`; subsequent runs must begin exactly one day after the stored watermark. If dates are omitted after bootstrap, TenderScope selects the next completed UTC day automatically.

```powershell
$env:TENDERSCOPE_STORAGE_ACCOUNT = "<storage-account-name>"
uv run python -m tenderscope.pipeline `
  --since 2026-11-12 `
  --until 2026-11-12 `
  --max-pages 2 `
  --state-policy enforce
```

See [Durable incremental state and recovery](docs/state-and-recovery.md) before bootstrapping or repairing a stream.

The `--allow-partial` flag is needed when the configured page limit is reached before the API's complete result set has been downloaded. It allows the available subset to be transformed and validated. For full extraction, use a sufficiently high `--max-pages` and run without `--allow-partial`.

The local pipeline performs five core steps:

1. Download TED API result pages into a run-specific Bronze directory.
2. Validate the Bronze manifest and read its notices.
3. Transform notices into three Silver Parquet datasets.
4. Run DuckDB data-quality checks; fail the run if any check fails.
5. Build run-level Gold summaries and a self-contained HTML report.

Cloud mode adds ADLS publication as step six. State-enforced mode adds the conditional watermark commit as step seven.

Each run gets a UTC-based identifier such as `ted_YYYYMMDDTHHMMSSffffffZ`.

### Resume an interrupted ingestion

```bash
uv run python -m tenderscope.pipeline --resume data/raw/ted_<run_id> --max-pages 10
```

Replace `<run_id>` with an existing run directory. The downloader uses the stored query, page manifest and next-page token to continue. Completed runs are not downloaded again.

The report distinguishes complete extraction from a partial sample, shows requested and observed dates separately, and counts distinct buyer names rather than resolved organizations. Cloud publication reserves each run ID once; retry a failed publication using a new run ID.

### Output

```text
data/
├── raw/
│   └── ted_<run_id>/
│       ├── manifest.json
│       ├── page_001.json
│       └── page_002.json
├── silver/
│   └── ted_<run_id>/
│       ├── notice.parquet
│       ├── notice_cpv.parquet
│       └── notice_buyer.parquet
└── gold/
    └── ted_<run_id>/
        ├── daily_summary.parquet
        ├── buyer_summary.parquet
        ├── cpv_summary.parquet
        ├── notice_type_summary.parquet
        ├── summary.json
        └── report.html
```

With ADLS publication enabled, the same run is uploaded as:

```text
bronze/runs/ted_<run_id>/manifest.json
bronze/runs/ted_<run_id>/page_*.json
silver/runs/ted_<run_id>/notice.parquet
silver/runs/ted_<run_id>/notice_cpv.parquet
silver/runs/ted_<run_id>/notice_buyer.parquet
silver/runs/ted_<run_id>/_SUCCESS.json
gold/runs/ted_<run_id>/daily_summary.parquet
gold/runs/ted_<run_id>/buyer_summary.parquet
gold/runs/ted_<run_id>/cpv_summary.parquet
gold/runs/ted_<run_id>/notice_type_summary.parquet
gold/runs/ted_<run_id>/summary.json
gold/runs/ted_<run_id>/report.html
```

| Silver dataset | Grain | Example fields |
| --- | --- | --- |
| `notice` | One row per notice | `notice_id`, `publication_date`, `title_pl`, `title_en`, `notice_type`, `xml_url` |
| `notice_cpv` | One row per unique notice–CPV pair | `notice_id`, `cpv_code` |
| `notice_buyer` | One row per unique notice–buyer name pair | `notice_id`, `buyer_name` |

## Reliability and data quality

**Ingestion safeguards**

- Retry of transient network errors and HTTP 429/5xx responses.
- Exponential backoff and support for numeric `Retry-After`.
- Iterative pagination using TED continuation tokens.
- Atomic writes for page files and the manifest.
- A per-run manifest with page counts, timestamps and resume state.
- Bronze record-count and page-sequence validation.
- Protection against silently accepting incomplete runs unless explicitly allowed.
- Inclusive `--since`/`--until` windows for controlled incremental batches.
- A versioned durable watermark committed only after `_SUCCESS`.
- Exact next-day enforcement prevents date gaps and overlaps.
- Conditional ETag writes reject stale or concurrent state updates.

**Silver quality gate (8 checks)**

1. Bronze and Silver notice counts match.
2. Notice IDs are unique.
3. Notice IDs are not null or blank.
4. Publication dates are not null.
5. Notice–CPV pairs are unique.
6. Notice–CPV records have matching notices.
7. Notice–buyer pairs are unique.
8. Notice–buyer records have matching notices.

A failed check raises an exception instead of silently reporting a successful run.

## Development

Run tests:

```bash
uv run pytest
```

Run the linter:

```bash
uv run ruff check .
```

Pull requests and pushes to `main` run Ruff, pytest, and a Docker image build in GitHub Actions. The workflow has read-only repository permissions and does not receive Azure credentials.

Dev deployments use a separate, manually approved OIDC workflow. See [Supervised dev deployment](docs/deployment.md) for its trust boundary and required GitHub environment configuration.

Azure resource definitions, adoption guidance and the optional project budget are documented in [Azure infrastructure](infra/README.md). Infrastructure and budget deployments are previewed with Azure `what-if` and are never applied by CI.

For a portfolio walkthrough, use the [short demonstration script](docs/demo.md). It shows the problem, architecture, CI, approval gate, cloud run and analytical result without exposing credentials.

## Roadmap

- [x] TED API ingestion with retries and iterative pagination
- [x] Bronze raw JSON and resumable manifest
- [x] Silver Parquet transformations
- [x] DuckDB Silver quality gate
- [x] Local pipeline entry point
- [x] ADLS Gen2 provisioning and standalone read/write/delete smoke test
- [x] Verify Docker build and container execution
- [x] Add CI checks (pytest, Ruff, Docker build)
- [x] Integrate quality-gated Bronze/Silver/Gold upload to ADLS Gen2
- [x] Deploy manual cloud execution with managed identity and verify an ADLS run
- [x] Describe the Azure platform and cost guardrails with Bicep
- [x] Add controlled incremental date windows while keeping execution manual
- [x] Add an approval-gated manual GitHub workflow for bounded ETL date windows
- [x] Persist a versioned watermark only after a complete, quality-gated run
- [x] Build run-level Gold analytical models and procurement KPIs
- [x] Add a zero-hosting-cost static dashboard report
- [ ] Add operational monitoring
- [x] Add source shape validation, a versioned Bronze contract and Silver schema compatibility checks

The unchecked items remain open. Their impact and priority are explained in [Current status and maturity](docs/project-status.md).

## Why this project?

TenderScope demonstrates practical Data Engineering patterns using a real public API: resilient ingestion, reproducible run-based raw storage, transformation into analytical datasets, relational modeling, automated data-quality gates and a path toward cloud deployment.

**Data source:** European Union [Tenders Electronic Daily (TED)](https://ted.europa.eu/). TenderScope is an independent portfolio project and is not affiliated with TED or the European Commission.

