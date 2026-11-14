# Project status and maturity

Last verified: **2026-11-14**

## Executive assessment

TenderScope is a **production-oriented portfolio MVP**. It is materially above a tutorial project: the pipeline handles retries and resumability, enforces data-quality gates, publishes three analytical layers, provisions Azure with Bicep, and uses approval-gated OIDC workflows with scoped identities.

It is not yet a production data product. It intentionally lacks automatic scheduling and still needs durable orchestration state, proactive monitoring, retention policies and formal schema evolution.

For portfolio calibration, the project demonstrates a **strong junior / junior-to-mid Data Engineering level**. The cloud security and delivery design push it above a typical junior CRUD or notebook portfolio project; the remaining operational gaps keep it below a mature production platform.

## What works now

| Area | Status | Evidence |
| --- | --- | --- |
| TED ingestion | Working | Iterative pagination, retry/backoff, atomic pages and resumable manifest |
| Incremental windows | Working, manual | Inclusive `since`/`until`; reversed and future windows rejected |
| Bronze | Working | Raw JSON, query metadata, timestamps and page counts |
| Silver | Working | Notice, buyer and CPV Parquet models |
| Data quality | Working | Eight DuckDB checks fail the pipeline on invalid data |
| Empty-day handling | Working | Typed empty Parquet models remain valid |
| Gold | Working | Four KPI summaries, JSON summary and static HTML report |
| ADLS publication | Working | Shared run ID and `_SUCCESS` marker written last |
| CI | Working | Ruff, pytest, Docker build and Bicep validation on PRs and `main` |
| Deployment | Working, supervised | Protected `dev`, OIDC, immutable image digest and post-deploy verification |
| Cloud ETL | Working, supervised | Manual date input, approval gate, one Azure execution and terminal-state polling |
| Infrastructure as code | Working | Bicep for ACR, ADLS, Container Apps, identities and scoped roles |

## Verified cloud evidence

- [Gold implementation PR #11](https://github.com/Mateusz0126/tenderscope/pull/11) passed CI and was merged to `main`.
- [Deploy dev run](https://github.com/Mateusz0126/tenderscope/actions/runs/43639549195) built, pushed and verified the Gold-capable image.
- [Run ETL dev #2](https://github.com/Mateusz0126/tenderscope/actions/runs/43640055844) waited for owner approval and completed successfully through OIDC.
- Azure execution published a shared run with 3 Bronze files, 3 Silver Parquet files, `_SUCCESS.json`, 4 Gold Parquet files, `summary.json` and `report.html`.
- The 2026-11-11 batch contained 16 notices, 13 unique buyers, 39 unique CPV codes and 3 notice types.

## Known gaps

| Priority | Gap | Why it matters | Sensible next step |
| --- | --- | --- | --- |
| P1 | No durable watermark | The next date is selected manually and can overlap or skip a day | Store the last complete date only after `_SUCCESS` |
| P1 | No proactive operational alert | A failed manual run is visible in GitHub but does not notify an operator outside GitHub | Add a low-cost failure notification and Azure alert |
| P1 | No schema evolution policy | Upstream TED field changes are detected indirectly by tests and transformations | Version Bronze/Silver contracts and add schema compatibility tests |
| P2 | No storage lifecycle policy | Old raw pages and reports accumulate indefinitely | Add reviewed retention tiers for dev data |
| P2 | No automated backfill orchestration | Windows are bounded and manually selected | Add a controlled backfill command with idempotent state |
| P2 | Report is not hosted | The HTML artifact must be downloaded or opened from storage | Keep it static or publish to a deliberately chosen low-cost host |
| P3 | No production SLO or disaster-recovery plan | Acceptable for a portfolio dev environment, not for a business service | Define freshness, recovery and ownership requirements first |

## Deliberate non-goals

- Always-on Spark or Databricks compute for a small bounded dataset.
- A paid BI service solely to display a portfolio dashboard.
- A client secret stored in GitHub.
- Automatic infrastructure deployment without a reviewed `what-if`.
- A schedule that can create cost without an explicit owner decision.

## Recommended next milestone

The highest-value engineering milestone is **durable incremental state plus failure notification**. It closes the main operational gap without changing the project's cost-controlled architecture. Hosting the report is presentation polish and should come after state correctness.
