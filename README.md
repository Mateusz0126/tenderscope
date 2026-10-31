# TenderScope

**An end-to-end Data Engineering project for exploring European public procurement notices.**

TenderScope ingests public tender notices from the [Tenders Electronic Daily (TED)](https://ted.europa.eu/) Search API, preserves raw responses in a Bronze layer, transforms them into analytical Parquet datasets in a Silver layer, and validates data quality with DuckDB.

> **Project status:** Working local Bronze → Silver pipeline with automated quality checks. Azure Data Lake Storage Gen2 connectivity has been smoke-tested separately. Cloud orchestration, CI/CD, and Gold analytics are planned.

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

Azure Data Lake Storage Gen2
  ├── bronze/   (provisioned; connectivity verified)
  └── silver/   (provisioned; connectivity verified)
```

The current pipeline writes datasets to the local filesystem. Automatic upload to ADLS Gen2 is **not yet integrated** into the pipeline.

## Tech stack

| Area | Technology |
| --- | --- |
| Language and packaging | Python 3.12+, uv |
| Data source | TED Search API v3 |
| API client | HTTPX |
| Data transformation | Polars |
| Storage format | JSON (Bronze), Parquet (Silver) |
| Data quality | DuckDB |
| Cloud storage (integration in progress) | Azure Data Lake Storage Gen2, Azure Identity |
| Containerization | Docker (Dockerfile available; runtime verification pending) |
| Testing and linting | pytest, Ruff |

## Current data scope

The default query selects notices where:

- Buyer country is **Poland** (`POL`).
- CPV classification matches **`72*`** (IT and related services).
- Publication date is within the **last 45 days**.
- Results are sorted by publication date, newest first.

The query is built in `src/tenderscope/ingestion/ted_api.py`. The ingestion code uses TED's iteration-based pagination with a page size of **50 notices**. By default, the pipeline processes at most **2 pages**, so a default run is a bounded sample, **not necessarily a complete extract** of all matching notices.

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
│   └── pipeline.py             # End-to-end orchestration
├── scripts/
│   └── smoke_adls.py           # Standalone ADLS connectivity smoke test
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

A Dockerfile is included for containerizing the pipeline. Its successful build and runtime behavior have not yet been verified as part of this README update.

## Roadmap

- [x] TED API ingestion with retries and iterative pagination
- [x] Bronze raw JSON and resumable manifest
- [x] Silver Parquet transformations
- [x] DuckDB Silver quality gate
- [x] Local pipeline entry point
- [x] ADLS Gen2 provisioning and standalone read/write/delete smoke test
- [ ] Verify Docker build and container execution
- [ ] Integrate automated Bronze/Silver upload to ADLS Gen2
- [ ] Add CI checks (pytest, Ruff, Docker build)
- [ ] Deploy scheduled cloud execution with managed identity
- [ ] Build Gold analytical models and procurement KPIs
- [ ] Add dashboard and operational monitoring

## Why this project?

TenderScope demonstrates practical Data Engineering patterns using a real public API: resilient ingestion, reproducible run-based raw storage, transformation into analytical datasets, relational modeling, automated data-quality gates and a path toward cloud deployment.

**Data source:** European Union [Tenders Electronic Daily (TED)](https://ted.europa.eu/). TenderScope is an independent portfolio project and is not affiliated with TED or the European Commission.
