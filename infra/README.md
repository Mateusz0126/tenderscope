# Azure infrastructure

TenderScope's dev infrastructure is described with Bicep so it can be reviewed, compared with Azure and recreated without storing credentials in the repository.

## Files

- `main.bicep` creates the resource group, least-privilege deployment role and platform module.
- `modules/platform.bicep` defines ACR, ADLS Gen2, Log Analytics, Container Apps, the runtime/deployment/runner identities, OIDC federation and scoped role assignments.
- `main.dev.bicepparam` records the current dev resource names and immutable image digest.
- `budget.bicep` is an optional, standalone resource-group budget. It is never deployed automatically.

The committed parameter file contains resource identifiers, not passwords. The budget notification email is a secure deployment-time parameter and must not be committed.

## Safety boundary

- The Container Apps Job uses a `Manual` trigger.
- Deploying infrastructure does not start the ETL job.
- GitHub's deployment identity can push an image and update only the existing job.
- The deployment identity cannot start or delete the job, read job secrets or access ADLS data.
- The runner identity can read and start only the existing job and monitor its executions. It cannot update, delete or stop the job, list secrets, push images or access ADLS directly.
- The runtime identity can pull from ACR, write the `bronze`, `silver` and `gold` data containers, and read/write only the durable watermark in the separate `control` container.

Azure permits callers with the job start action to supply a one-time execution template. The runner identity is therefore protected by the immutable GitHub environment OIDC subject, `main`-only workflow execution and manual `dev` approval in addition to its job-scoped custom role.

The `control` container holds only versioned orchestration state. It is separated from analytical layers so data consumers do not need access to mutable control-plane files. The runtime identity uses ETag preconditions when updating that state; role scope alone does not replace application-level concurrency control.

## Validate locally

```powershell
az bicep build --file infra/main.bicep
az bicep build-params --file infra/main.dev.bicepparam
az bicep build --file infra/budget.bicep
```

Generated ARM JSON files are ignored by Git and should not be committed.

## Preview changes

Always run a subscription-level what-if before applying the platform template:

```powershell
$currentImage = az containerapp job show `
  --resource-group rg-tenderscope-dev `
  --name caj-tenderscope-etl-dev `
  --query properties.template.containers[0].image `
  --output tsv

az deployment sub what-if `
  --location polandcentral `
  --template-file infra/main.bicep `
  --parameters infra/main.dev.bicepparam `
  --parameters initialContainerImage=$currentImage
```

The current role-assignment names are preserved in `main.dev.bicepparam`. This lets Bicep adopt the existing dev permissions instead of creating duplicate assignments.

The image digest in `main.dev.bicepparam` records the infrastructure snapshot at the time it was committed. GitHub Actions owns later application image updates. Always override `initialContainerImage` with the job's current image, as shown above, so an infrastructure deployment cannot roll the application back. Use the same override if `what-if` is deliberately replaced with `create` after review.

Azure `what-if` may display calculated resource references, such as a managed identity principal ID, as modifications even when they resolve to the current value. Treat any concrete create, delete, permission or image change as a reason to stop and investigate.

## Budget guardrail

The Azure subscription already has a monthly budget alert configured outside this repository. The project-level budget is therefore optional and must be deliberately deployed with an email supplied interactively:

```powershell
az deployment group what-if `
  --resource-group rg-tenderscope-dev `
  --template-file infra/budget.bicep `
  --parameters monthlyBudgetAmount=15 notificationEmail='<your-email>'
```

Replace `what-if` with `create` only after reviewing the preview. Azure budgets send notifications; they do not automatically stop or delete resources.

## Cost posture

- ETL executions remain manual and bounded to two TED pages by the current container command.
- Log Analytics retains data for 30 days.
- ACR uses the Basic tier and storage uses Standard LRS.
- No paid analytics database, scheduler or dashboard resource is provisioned.
- Review Azure Cost Analysis after deployments because cost data can arrive with a delay.

