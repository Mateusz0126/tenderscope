# Demonstration checklist

Use existing successful runs; a live ETL is optional. Keep credentials and environment secrets off screen.

## Explain the data

TED publishes procurement notices. TenderScope currently selects Polish buyers and IT-related CPV codes. A publication is not necessarily a distinct procurement procedure, and buyer names are not verified organization identities.

## Follow one batch

Show the original query and page count in Bronze, the three Silver tables and the quality gate. Then show the shared run ID in the publication marker and Gold report. Explain how partial extraction differs from a complete empty day.

## Show one failure case

Use the failed-publication test: a run ID is reserved before upload, so retrying it cannot alter previously published data. Another test shows that the watermark advances only after publication. Explain why a retry uses a new run ID.

## Show delivery

Open a successful CI run and a deployment. CI checks Python, tests, Docker and Bicep. Deployment and ETL are separate manual workflows with protected `dev` approval and separate Azure identities. A successful state-enforced ETL advances the watermark automatically; there is no scheduler.

## Show history

Open `catalogs/dev-history.json`, then the daily summary from [the history walkthrough](history.md). It contains 27, 26 and zero notices for 12–14 November. Point to the source run IDs. Explain why scanning every successful run would double-count retries and why a correction replaces an entire reviewed window.

## Explain the remaining work

Historical selection is manual. Automated detection of source corrections, proactive alerts, retention policies and the Power BI model are not implemented. The project has working cloud execution and a local historical builder; it has not been benchmarked as a large-scale production service.
