# Supervised dev deployment and ETL execution

TenderScope uses GitHub Actions OpenID Connect (OIDC) to deploy to Azure without a client secret or a stored Azure password.

## Deployment boundary

The `Deploy dev` workflow:

1. can only run manually from the `main` branch;
2. waits for approval of the protected GitHub environment named `dev`;
3. receives a short-lived Azure token through OIDC;
4. builds and pushes an image tagged with the Git commit SHA;
5. resolves the registry digest and updates the Container Apps Job to that immutable image;
6. verifies the configured image;
7. does **not** start the job.

The job remains intentionally manual after the first successful, quality-gated Bronze, Silver and Gold publication to ADLS Gen2. This keeps every data run and its cost under the repository owner's control.

The separate `Run ETL dev` workflow accepts an inclusive historical date window, waits for the same `dev` approval, starts exactly one execution and waits for its terminal status. It has no schedule.

## GitHub environment

Create an environment named `dev` in **Settings → Environments**.

Configure:

- required reviewer: the repository owner;
- deployment branch: `main` only;
- prevent self-review: disabled while the repository has only one maintainer.

Add these environment secrets:

| Name | Azure source |
| --- | --- |
| `AZURE_CLIENT_ID` | Client ID of `mi-tenderscope-github-dev` |
| `AZURE_ETL_CLIENT_ID` | Client ID of `mi-tenderscope-runner-dev` |
| `AZURE_TENANT_ID` | Tenant ID of the Azure subscription |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |

These values identify the Azure identity and subscription. They are not passwords. The workflow has no client secret; storing them as environment secrets prevents unnecessary disclosure in the public repository and follows the input-hardening guidance of `azure/login`.

Add these environment variables:

| Name | Value |
| --- | --- |
| `AZURE_RESOURCE_GROUP` | `rg-tenderscope-dev` |
| `AZURE_ACR_NAME` | `acrtenderscope70385` |
| `AZURE_JOB_NAME` | `caj-tenderscope-etl-dev` |
| `AZURE_IMAGE_REPOSITORY` | `tenderscope-etl` |

## Azure trust and authorization

The user-assigned managed identity `mi-tenderscope-github-dev` trusts only the immutable repository and owner IDs for the protected `dev` environment:

```text
repo:Mateusz0126@29069191/tenderscope@1440847144:environment:dev
```

Its Azure access is limited to:

- `AcrPush` on the TenderScope Azure Container Registry;
- the custom `TenderScope Container Apps Job Deployer` role on `caj-tenderscope-etl-dev` only.

The custom role can read and update the job. It cannot start or delete the job, list job secrets, modify role assignments, or access ADLS data.

The runtime identity `mi-tenderscope-job-dev` remains separate. It pulls the image, writes the `bronze`, `silver` and `gold` containers, and reads/conditionally writes the watermark in the private `control` container.

The ETL runner identity `mi-tenderscope-runner-dev` has the custom `TenderScope Container Apps Job Runner` role on this job only. The role contains only job read, execution read and job start actions. It cannot update or delete the job, stop executions, list secrets, modify role assignments, push images or access ADLS directly.

Azure's start operation can accept a one-time execution template. Consequently, any identity with `Microsoft.App/jobs/start/action` must be treated as trusted to use the job's configured secrets and managed identities. TenderScope reduces that risk by using a dedicated identity, an immutable repository/environment OIDC subject, `main`-only workflow execution, environment approval, fixed workflow code and a job-scoped role assignment.

The matching Bicep definitions are in [`infra/`](../infra/README.md). CI validates them but never deploys infrastructure or starts the ETL job.

## Manual incremental execution in GitHub

Open **Actions → Run ETL dev → Run workflow** on `main`, then enter `since` and `until` as ISO dates. The workflow enforces:

- completed historical dates only;
- an inclusive window of at most seven days;
- the currently deployed image pinned by SHA-256 digest;
- one active GitHub workflow at a time;
- a maximum execution wait of 30 minutes.
- a durable watermark that rejects gaps, overlaps and stale concurrent writers.

Choose the dates deliberately before each run. The first state-enforced run bootstraps the stream; every later run must start on the exact next date reported by the watermark. Keep `--allow-partial` disabled so a page-limited subset cannot advance durable state.

For a new environment, deploy the reviewed Bicep configuration with the `control` container and its scoped runtime role before the first state-enforced execution. For an existing stream, read `last_completed_date` from `control/state/ted-poland-it.json` and set `since` to the next calendar day. Check the execution and matching completion marker using [Durable incremental state and recovery](state-and-recovery.md).


## Page limits and diagnostics

`Run ETL dev` accepts `max_pages` from 1 through 100 (default 2, up to 50 notices per page). Increase it deliberately for larger windows. Reaching the limit while more data exists still fails publication and leaves the watermark unchanged. The seven-day and execution-time limits remain in place.

The final workflow summary reports the requested dates, page limit, image digest, Azure execution, observed status and failed workflow stages, including failures before ETL starts. A polling timeout does not cancel Azure execution. Check the execution logs and watermark before retrying. The summary is diagnostic output, not proactive notification; no new alert resources are provisioned.

Publication IDs are single-use. After a cloud upload failure, retry the same date window as a new run. Existing reports keep their old format until a new batch is generated with the updated image.
