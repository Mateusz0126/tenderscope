# TenderScope

**An end-to-end Data Engineering project for exploring European public procurement notices.**

TenderScope ingests public tender notices from the [Tenders Electronic Daily (TED)](https://ted.europa.eu/) Search API, preserves raw responses in a Bronze layer, transforms them into analytical Parquet datasets in a Silver layer, and validates data quality with DuckDB.

> **Project status:** Working Bronze → Silver pipeline with automated quality checks, ADLS Gen2 publication, pull-request CI, an approval-gated Azure deployment workflow, and a successful reviewed cloud data run. The Container Apps Job remains intentionally manual to keep execution and cost under owner control.

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
         | publish only after the quality gate passes
         v
Azure Data Lake Storage Gen2
  ├── bronze/runs/<run_id>/
  └── silver/runs/<run_id>/
      └── _SUCCESS.json
```

The pipeline always writes and validates local working files first. When `TENDERSCOPE_STORAGE_ACCOUNT` is configured, it then uploads Bronze and Silver files to ADLS Gen2. The Silver `_SUCCESS.json` marker is written last, so consumers can distinguish complete runs from interrupted uploads.

## Tech stack

| Area | Technology |
| --- | --- |
| Language and packaging | Python 3.12+, uv |
| Data source | TED Search API v3 |
| API client | HTTPX |
| Data transformation | Polars |
| Storage format | JSON (Bronze), Parquet (Silver) |
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

## Repository structure

```text
.
├── src/tenderscope/
│   ├── ingestion/
│   │   ├── ted_api.py          # TED endpoint, fields and query
│   │   └── ted_pages.py        # Pagination, retry, checkpoints and manifests
│   ├── transformations/
│   │   ├── bronze_reader.py    # Read and validate raw page files
│   │   └── silver.py           # Normalize notices and write Parquet
│   ├── quality/
│   │   └── silver.py           # DuckDB data-quality gate
│   ├── storage/
│   │   └── adls.py             # Idempotent Bronze/Silver publication
│   └── pipeline.py             # End-to-end orchestration
├── scripts/
│   └── smoke_adls.py           # Standalone ADLS connectivity smoke test
├── infra/                      # Reproducible Azure Bicep templates
├── Dockerfile
├── .dockerignore
├── pyproject.toml
└── README.md
```

Local runtime output is stored under `data/raw/` and `data/silver/`, both ignored by Git.

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

The `--allow-partial` flag is needed when the configured page limit is reached before the API's complete result set has been downloaded. It allows the available subset to be transformed and validated. For full extraction, use a sufficiently high `--max-pages` and run without `--allow-partial`.

The pipeline performs four steps:

1. Download TED API result pages into a run-specific Bronze directory.
2. Validate the Bronze manifest and read its notices.
3. Transform notices into three Silver Parquet datasets.
4. Run DuckDB data-quality checks; fail the run if any check fails.

Each run gets a UTC-based identifier such as `ted_YYYYMMDDTHHMMSSffffffZ`.

### Resume an interrupted ingestion

```bash
uv run python -m tenderscope.pipeline --resume data/raw/ted_<run_id> --max-pages 10
```

Replace `<run_id>` with an existing run directory. The downloader uses the stored query, page manifest and next-page token to continue. Completed runs are not downloaded again.

### Output

```text
data/
├── raw/
│   └── ted_<run_id>/
│       ├── manifest.json
│       ├── page_001.json
│       └── page_002.json
└── silver/
    └── ted_<run_id>/
        ├── notice.parquet
        ├── notice_cpv.parquet
        └── notice_buyer.parquet
```

With ADLS publication enabled, the same run is uploaded as:

```text
bronze/runs/ted_<run_id>/manifest.json
bronze/runs/ted_<run_id>/page_*.json
silver/runs/ted_<run_id>/notice.parquet
silver/runs/ted_<run_id>/notice_cpv.parquet
silver/runs/ted_<run_id>/notice_buyer.parquet
silver/runs/ted_<run_id>/_SUCCESS.json
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

## Roadmap

- [x] TED API ingestion with retries and iterative pagination
- [x] Bronze raw JSON and resumable manifest
- [x] Silver Parquet transformations
- [x] DuckDB Silver quality gate
- [x] Local pipeline entry point
- [x] ADLS Gen2 provisioning and standalone read/write/delete smoke test
- [x] Verify Docker build and container execution
- [x] Add CI checks (pytest, Ruff, Docker build)
- [x] Integrate quality-gated Bronze/Silver upload to ADLS Gen2
- [x] Deploy manual cloud execution with managed identity and verify an ADLS run
- [x] Describe the Azure platform and cost guardrails with Bicep
- [x] Add controlled incremental date windows while keeping execution manual
- [ ] Persist a watermark only after a complete, quality-gated run
- [ ] Build Gold analytical models and procurement KPIs
- [ ] Add dashboard and operational monitoring

## Why this project?

TenderScope demonstrates practical Data Engineering patterns using a real public API: resilient ingestion, reproducible run-based raw storage, transformation into analytical datasets, relational modeling, automated data-quality gates and a path toward cloud deployment.

**Data source:** European Union [Tenders Electronic Daily (TED)](https://ted.europa.eu/). TenderScope is an independent portfolio project and is not affiliated with TED or the European Commission.
