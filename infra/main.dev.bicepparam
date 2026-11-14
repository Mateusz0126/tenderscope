using './main.bicep'

param location = 'polandcentral'
param resourceGroupName = 'rg-tenderscope-dev'
param initialContainerImage = 'acrtenderscope70385.azurecr.io/tenderscope-etl@sha256:209255293ca15ce9102e61eaba4c9e96e45332fd02eb12505eab6b25d1f83ae3'
param githubOidcSubject = 'repo:Mateusz0126@29069191/tenderscope@1440847144:environment:dev'

param names = {
  containerRegistry: 'acrtenderscope70385'
  storageAccount: 'sttenderscope123123'
  logAnalyticsWorkspace: 'workspace-rgtenderscopedevaC8H'
  containerAppsEnvironment: 'cae-tenderscope-dev'
  containerAppJob: 'caj-tenderscope-etl-dev'
  runtimeIdentity: 'mi-tenderscope-job-dev'
  deploymentIdentity: 'mi-tenderscope-github-dev'
}

param roleAssignmentNames = {
  runtimeAcrPull: '785f5289-cdc4-4728-a1b2-f8516cc77ac2'
  runtimeBronzeContributor: '959b648b-f875-482b-98f8-7c89937df6d0'
  runtimeSilverContributor: '941ab002-a2f5-40b0-8493-c65497f94c4e'
  deploymentAcrPush: '65b23256-bf36-4b03-a9ed-60ce94743d77'
  deploymentJobUpdater: '8fc330a2-b141-4dd9-967a-dc0446892111'
}
