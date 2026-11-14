targetScope = 'resourceGroup'

param location string
param initialContainerImage string
param githubOidcSubject string
param jobDeployerRoleDefinitionId string
param jobRunnerRoleDefinitionId string
param names object
param roleAssignmentNames object = {}

var platformTags = {
  environment: 'dev'
  'managed-by': 'bootstrap'
  project: 'TenderScope'
}

var acrPullRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7f951dda-4ed3-4680-a7ca-43fe172d538d'
)
var acrPushRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '8311e382-0749-4cb8-b61a-304f252e45ec'
)
var storageBlobDataContributorRoleDefinitionId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: names.logAnalyticsWorkspace
  location: location
  properties: {
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: names.containerAppsEnvironment
  location: location
  tags: platformTags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    peerAuthentication: {
      mtls: {
        enabled: false
      }
    }
    peerTrafficConfiguration: {
      encryption: {
        enabled: false
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: names.containerRegistry
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    dataEndpointEnabled: false
    encryption: {
      status: 'disabled'
    }
    publicNetworkAccess: 'Enabled'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: names.storageAccount
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    allowBlobPublicAccess: false
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    containerDeleteRetentionPolicy: {
      days: 7
      enabled: true
    }
    deleteRetentionPolicy: {
      allowPermanentDelete: false
      days: 7
      enabled: true
    }
  }
}

resource bronze 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'bronze'
  properties: {
    defaultEncryptionScope: '$account-encryption-key'
    denyEncryptionScopeOverride: false
    publicAccess: 'None'
  }
}

resource silver 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'silver'
  properties: {
    defaultEncryptionScope: '$account-encryption-key'
    denyEncryptionScopeOverride: false
    publicAccess: 'None'
  }
}

resource runtimeIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.runtimeIdentity
  location: location
}

resource deploymentIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.deploymentIdentity
  location: location
  tags: {
    environment: 'dev'
    project: 'TenderScope'
    purpose: 'github-deployment'
  }
}

resource runnerIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.runnerIdentity
  location: location
  tags: {
    environment: 'dev'
    project: 'TenderScope'
    purpose: 'github-etl-runner'
  }
}

resource githubFederatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: deploymentIdentity
  name: 'fic-github-tenderscope-dev'
  properties: {
    audiences: [
      'api://AzureADTokenExchange'
    ]
    issuer: 'https://token.actions.githubusercontent.com'
    subject: githubOidcSubject
  }
}

resource runnerGithubFederatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: runnerIdentity
  name: 'fic-github-tenderscope-runner-dev'
  properties: {
    audiences: [
      'api://AzureADTokenExchange'
    ]
    issuer: 'https://token.actions.githubusercontent.com'
    subject: githubOidcSubject
  }
}

resource job 'Microsoft.App/jobs@2025-01-01' = {
  name: names.containerAppJob
  location: location
  tags: platformTags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${runtimeIdentity.id}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 1
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: runtimeIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: names.containerAppJob
          image: initialContainerImage
          env: [
            {
              name: 'TENDERSCOPE_STORAGE_ACCOUNT'
              value: storage.name
            }
            {
              name: 'TENDERSCOPE_STORAGE_PREFIX'
              value: 'runs'
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: runtimeIdentity.properties.clientId
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
    }
  }
}

resource runtimeAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: roleAssignmentNames.?runtimeAcrPull ?? guid(registry.id, runtimeIdentity.id, acrPullRoleDefinitionId)
  properties: {
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRoleDefinitionId
  }
}

resource runtimeBronzeContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: bronze
  name: roleAssignmentNames.?runtimeBronzeContributor ?? guid(bronze.id, runtimeIdentity.id, storageBlobDataContributorRoleDefinitionId)
  properties: {
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: storageBlobDataContributorRoleDefinitionId
  }
}

resource runtimeSilverContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: silver
  name: roleAssignmentNames.?runtimeSilverContributor ?? guid(silver.id, runtimeIdentity.id, storageBlobDataContributorRoleDefinitionId)
  properties: {
    principalId: runtimeIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: storageBlobDataContributorRoleDefinitionId
  }
}

resource deploymentAcrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: roleAssignmentNames.?deploymentAcrPush ?? guid(registry.id, deploymentIdentity.id, acrPushRoleDefinitionId)
  properties: {
    principalId: deploymentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPushRoleDefinitionId
  }
}

resource deploymentJobUpdater 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: job
  name: roleAssignmentNames.?deploymentJobUpdater ?? guid(job.id, deploymentIdentity.id, jobDeployerRoleDefinitionId)
  properties: {
    principalId: deploymentIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: jobDeployerRoleDefinitionId
  }
}

resource runnerJobStarter 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: job
  name: roleAssignmentNames.?runnerJobStarter ?? guid(job.id, runnerIdentity.id, jobRunnerRoleDefinitionId)
  properties: {
    principalId: runnerIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: jobRunnerRoleDefinitionId
  }
}

output containerAppJobName string = job.name
output deploymentIdentityName string = deploymentIdentity.name
output runnerIdentityName string = runnerIdentity.name
output runtimeIdentityName string = runtimeIdentity.name
