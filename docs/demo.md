# TenderScope demonstration

This walkthrough presents the project in five to seven minutes without exposing credentials or spending money on an unnecessary always-on service.

## Before the call

- Keep the repository, the latest successful CI run and Azure Storage browser available in separate tabs.
- Use a completed historical day with a small result set if a live ETL run is planned.
- Never show environment secret values, access tokens, storage keys or local credential files.
- A live cloud run is optional. The verified run from 2026-11-14 is sufficient evidence if time is limited.

## 1. Frame the problem

> TenderScope turns public TED procurement notices into quality-gated analytical datasets. I focused the sample on Polish buyers and IT-related CPV codes, then designed the pipeline so every batch is reproducible and traceable across Bronze, Silver and Gold.

Show the first screen of `README.md`, especially the capability table and verified run.

## 2. Explain the architecture

Open [architecture.md](architecture.md) and cover three points:

1. raw API evidence is kept separately from transformed models;
2. quality checks run before any cloud publication is marked complete;
3. deployment, execution and runtime access use separate Azure identities.

The strongest engineering story is not the number of Azure resources. It is the explicit trust boundary and failure behavior.

## 3. Show engineering quality

Open the latest CI run and point out:

- Ruff;
- pytest;
- Docker build;
- Bicep compilation;
- read-only repository permissions.

Then show one focused test, such as the failed-upload or empty-day pipeline test, instead of scrolling through the entire test suite.

## 4. Show supervised delivery

Open `Actions → Deploy dev` and explain:

- the workflow runs only from `main`;
- the protected `dev` environment requires owner approval;
- GitHub obtains a short-lived Azure token through OIDC;
- the image is deployed by immutable digest;
- deploying the image does not start the ETL job.

## 5. Show a data run

Open `Actions → Run ETL dev`, select a completed historical window and explain the safeguards:

- maximum seven inclusive days;
- one workflow at a time;
- protected-environment approval;
- manual Container Apps execution;
- 30-minute timeout;
- no automatic schedule or watermark advancement.

For a live demo, approve the run yourself and wait for `Succeeded`. Otherwise open the [verified run](https://github.com/Mateusz0126/tenderscope/actions/runs/43640055844).

## 6. Show the result

In ADLS, use the shared run identifier to move through:

1. `bronze/runs/<run_id>/manifest.json`;
2. `silver/runs/<run_id>/_SUCCESS.json`;
3. `gold/runs/<run_id>/summary.json`;
4. `gold/runs/<run_id>/report.html`.

For the verified 2026-11-11 batch, call out 16 notices, 13 unique buyers, 39 unique CPV codes and 3 notice types.

## 7. Finish with trade-offs

> This is a production-oriented portfolio MVP, not a production service. It has secure delivery, resumable ingestion, quality gates and verified cloud execution. The next production priorities would be a durable watermark, operational alerts, schema-version handling and lifecycle policies. I deliberately kept execution manual to control cost and make deployment decisions reviewable.

That conclusion is stronger than claiming the project is finished in every production dimension.
