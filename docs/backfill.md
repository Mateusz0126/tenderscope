# Filling earlier dates

Backfill retrieves dates before the current incremental watermark. It uses the existing Container Apps Job and protected `dev` approval. It does not create a schedule, provision resources, move the watermark or automatically change the historical catalog.

## Two execution modes

| Mode | State | Publication prefix |
| --- | --- | --- |
| `incremental` (default) | Requires the next contiguous date; commits state after success | `runs` |
| `backfill` | Does not read or commit the watermark | `backfills/<since>_<until>` |

Both modes reject future/current UTC days and windows longer than seven inclusive days. Both require complete extraction, use a unique run ID, and allow a page limit from 1 to 100. Increasing a limit permits more work; it does not guarantee that an entire week fits.

## First supervised batch

After merging this workflow change, use **Actions → Run ETL dev → Run workflow**:

- branch: `main`;
- mode: `backfill`;
- since: `2026-11-05`;
- until: `2026-11-11`;
- max_pages: `10`.

Review the dates and mode before approving `dev`. This is a proposed pilot, not a record of an executed run. The application already supports the required arguments; this workflow change alone does not require a new application deployment if the currently deployed image includes the publication/report fixes from PR #17.

The workflow executes the currently deployed image by digest. No new image is built for a backfill. The summary records mode, dates, image, page limit, storage prefix and state policy.

## Verify before accepting the data

1. Record the incremental watermark and its ETag before execution. Check that no incremental run is active.
2. Wait for Azure execution success, then confirm the watermark and ETag did not change.
3. Find the run ID under `bronze/backfills/<since>_<until>/`. Check the exact query and completed manifest, matching Silver `_SUCCESS.json`, and Gold report.
4. Review the record counts and any unexpected data. If ingestion hit its page limit, the batch is not eligible for history. Retry the window with a reviewed larger limit or split it into smaller windows.
5. Add the accepted run to the catalog in a separate PR. Set `prefix` to `backfills/<since>_<until>`, keep the real run ID and record the workflow evidence in `reason`.
6. Extend the catalog date range and rebuild a new snapshot using the [history commands](history.md). Coverage must remain contiguous.

When a new batch overlaps an already accepted window, do not add both. Use the explicit whole-window replacement rule or choose non-overlapping batches. The storage prefix does not make a batch authoritative; catalog review does.

## Expanding the history

Start with the single pilot. If it passes, extend backwards in reviewed windows, for example 29 October–4 November followed by 22–28 October. Keep each request bounded and inspect the first larger run before raising limits. Source availability and completeness are checked by the pipeline; historical data is not assumed to be available indefinitely.

A failure before publication leaves the watermark unchanged. A failed publication may leave an incomplete reserved run; retry with a new run ID. A GitHub polling timeout does not stop an Azure execution. Inspect its status before starting another attempt. The existing job has a 30-minute replica timeout and one retry, so polling timeout is not a hard cost cap for the whole execution.

Automatic collection every two days is a separate change: it needs date selection from the watermark, failure handling and an explicit decision about unattended execution. The current workflow remains manual.
