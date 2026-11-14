# Supervised dev deployment

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

The job remains intentionally manual after the first successful, quality-gated Bronze and Silver publication to ADLS Gen2. This keeps every data run and its cost under the repository owner's control.

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

The runtime identity `mi-tenderscope-job-dev` remains separate. It pulls the image and accesses only the `bronze` and `silver` containers.

The matching Bicep definitions are in [`infra/`](../infra/README.md). CI validates them but never deploys infrastructure or starts the ETL job.

## Manual incremental execution

After an approved deployment, a single execution can override the container arguments without changing the job's manual trigger or stored schedule:

```powershell
az containerapp job start `
  --resource-group rg-tenderscope-dev `
  --name caj-tenderscope-etl-dev `
  --container-name caj-tenderscope-etl-dev `
  --args "--max-pages" "2" `
         "--since" "2026-11-02" "--until" "2026-11-02"
```

Choose the dates deliberately before each run. Until a durable watermark is implemented, TenderScope does not infer or advance the next date automatically. Keep `--allow-partial` disabled for incremental batches so a page limit cannot be mistaken for a completed date window.
