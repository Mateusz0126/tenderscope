# Project status and maturity

Last verified: **2026-11-16**

## Current scope

TenderScope processes bounded TED date windows in Azure dev. The workflow uses retries and resumable ingestion, blocking quality checks, three analytical layers, and approval-gated OIDC with scoped identities. Operators choose which window to run. Proactive monitoring, retention policies, and automatic historical reconciliation remain open.

## What works now

| Area | Status | Evidence |
| --- | --- | --- |
| TED ingestion | Working | Iterative pagination, retry/backoff, atomic pages and resumable manifest |
| Incremental windows | Working, manual | Inclusive `since`/`until`; reversed and future windows rejected |
| Durable state | Bootstrap and updates verified in Azure | Versioned JSON, matching completion marker and changed ETag after successful runs |
| Bronze | Working | Raw JSON, query metadata, timestamps and page counts |
| Silver | Working | Notice, buyer and CPV Parquet models |
| Data quality | Working | Eight DuckDB checks fail the pipeline on invalid data |
| Empty-day handling | Working | Typed empty Parquet models remain valid |
| Gold | Working | Four KPI summaries, JSON summary and static HTML report |
| Power BI | Local Desktop import and DAX verified | Two-page PBIP starter; distinct notices, complete-day coverage, CPV filters and source provenance |
| History | Local build verified using Azure inputs | Reviewed catalog, whole-window replacements, provenance and complete date coverage |
| ADLS publication | Working | Shared run ID and `_SUCCESS` marker written after all data files and before committing state |
| CI | Working | Ruff, pytest, Docker build and Bicep validation on PRs and `main` |
| Deployment | Working, supervised | Protected `dev`, OIDC, immutable image digest and post-deploy verification |
| Cloud ETL | Working, supervised | Manual date input, approval gate, one Azure execution and terminal-state polling |
| Infrastructure as code | Working | Bicep for ACR, ADLS, Container Apps, identities and scoped roles |

## Verified cloud evidence

- [Gold implementation PR #11](https://github.com/Mateusz0126/tenderscope/pull/11) passed CI and was merged to `main`.
- [Deploy dev run](https://github.com/Mateusz0126/tenderscope/actions/runs/43639549195) built, pushed and verified the Gold-capable image.
- [Run ETL dev #2](https://github.com/Mateusz0126/tenderscope/actions/runs/43640055844) waited for owner approval and completed successfully through OIDC.
- Azure execution published a shared run with 3 Bronze files, 3 Silver Parquet files, `_SUCCESS.json`, 4 Gold Parquet files, `summary.json` and `report.html`.
- The 2026-11-11 batch contained 16 notices, 13 distinct buyer names, 39 unique CPV codes and 3 notice types.
- The [2026-11-12 ETL](https://github.com/Mateusz0126/tenderscope/actions/runs/43757352887) created the watermark. The stored date, ETag and `_SUCCESS` for its `last_run_id` were checked in ADLS.

## Known gaps

| Priority | Gap | Why it matters | Sensible next step |
| --- | --- | --- | --- |
| P1 | No proactive operational alert | A failed manual run is visible in GitHub but does not notify an operator outside GitHub | Add a low-cost failure notification and Azure alert |
| P2 | No automatic historical reconciliation | The watermark does not revisit corrected historical data | Use the reviewed history catalog; add source reconciliation only when needed |
| P2 | No storage lifecycle policy | Old raw pages and reports accumulate indefinitely | Add reviewed retention tiers for dev data |
| P2 | Historical extraction remains manual | Backfill mode prepares bounded batches, but no catch-up loop or schedule exists | Verify the first supervised backfill before extending the date range |
| P2 | Report is not hosted | The HTML artifact must be downloaded or opened from storage | Keep it static or publish to a deliberately chosen low-cost host |
| P3 | No production SLO or disaster-recovery plan | Acceptable for a portfolio dev environment, not for a business service | Define freshness, recovery and ownership requirements first |

## Deliberate non-goals

- Always-on Spark or Databricks compute for a small bounded dataset.
- A paid BI service solely to display a portfolio dashboard.
- A client secret stored in GitHub.
- Automatic infrastructure deployment without a reviewed `what-if`.
- A schedule that can create cost without an explicit owner decision.

## Next milestone

The Power BI starter defines a local import model, distinct-notice measures and two report pages; see [setup and acceptance checks](powerbi.md). Extend the reviewed history through a supervised backfill before interpreting trends. Proactive failure notifications and retention remain operational follow-ups.

## Reliability hardening

The publication protocol now rejects reuse of completed or reserved run IDs, including legacy successes. Regression tests cover a failed second publication and actual SDK conditional headers. Report metadata separates completeness from quality and preserves empty requested windows. Source compatibility and exact Silver schema checks are enforced; see [data contracts](data-contracts.md).

The ETL workflow offers a bounded page limit and an always-run diagnostic summary. The [14 November empty-day run](https://github.com/Mateusz0126/tenderscope/actions/runs/43833398567) verified the new reservation, report metadata and watermark update in Azure. Proactive alerts and automated retention remain open.

On 16 November the historical builder combined existing batches for 12–14 November into 53 notices with source run IDs. This was a local build from Azure inputs, not a deployed historical service. See [history](history.md).

The manual workflow now offers a separate backfill mode. It has workflow/CLI tests but has not yet been verified through an Azure backfill execution. See [the pilot plan](backfill.md).
