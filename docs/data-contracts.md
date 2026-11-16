# Data contracts and corrections

## Version 1

The Bronze manifest now writes `schema_version: 1`. Manifests without a version are treated as legacy v1; unknown versions fail before transformation or resume. This version describes the stored envelope, not TED's upstream API version.

The source contract requires a publication number and a parseable publication date. Optional title translations must be strings, buyer translations lists of strings, CPV codes eight-digit strings, and XML links objects containing a string URL when present. Missing optional fields remain allowed. Additive upstream fields are ignored by Silver but retained in Bronze. Incompatible known fields fail explicitly; they are not silently dropped.

Silver v1 is defined by the three schema constants in `transformations/silver.py`. Quality validation checks names and types before the eight relational checks. Missing, extra or differently typed columns require a reviewed contract change. This is a deliberately conservative compatibility policy.

Gold `summary.json` has `schema_version: 1`, extraction status, the original query, requested bounds, observed dates and metric definitions. The existing `unique_buyers` key is retained for consumer compatibility, but means distinct buyer-name strings. It is not an organization count. `notices` counts publication records, not distinct procurement procedures.

## Completeness

`completed` means that pagination finished for that query at extraction time. It does not promise that TED will never correct or add historical records. `partial` is a bounded sample. `unknown` is used when Gold is built without a Bronze manifest. Quality results are reported separately from completeness. Empty completed windows preserve their requested bounds and have no observed dates.

The HTML report displays this distinction. Existing cloud reports are not rewritten by a code deployment.

## Historical corrections

The production-style incremental path remains contiguous and never rewinds its watermark. Do not edit the watermark or reuse a published run ID to repair history.

For a historical discrepancy:

1. Record the dates, reason and original run ID in a reviewed change or incident note.
2. Re-extract locally with explicit `--since` and `--until`, `--state-policy off`, without a storage account and without `--allow-partial`. Unset `TENDERSCOPE_STORAGE_ACCOUNT` if it is present. Choose a page limit that completes the extraction.
3. Compare notice IDs and values with the original batch. Review additions, removals and changed fields; a different row count alone is not approval.
4. If cloud publication is approved, use a new run ID and a separate `--storage-prefix corrections/<review-id>`, keep `--state-policy off`, and require a complete, validated batch.
5. Record the replacement run, original run, dates and approval in the same review. Downstream analysis must explicitly select that replacement rather than union both runs.

The normal GitHub workflow cannot execute corrections or disable state enforcement. Automatic historical reconciliation and a machine-readable catalog of accepted replacements are not implemented. Until a catalog exists, cross-run aggregation must not blindly scan every successful run: at-least-once publication can produce duplicate windows.

## Evolving a contract

An incompatible change needs a new contract version, migration or separate output namespace, representative old/new fixtures, and an explicit reader compatibility decision. Do not silently reinterpret existing columns. Source shape tests and Silver schema tests run in CI; Azure integration remains a separate supervised check.
