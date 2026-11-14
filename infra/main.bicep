targetScope = 'subscription'

@description('Azure region used by all TenderScope resources.')
param location string = 'polandcentral'

@description('Resource group that contains the dev environment.')
param resourceGroupName string = 'rg-tenderscope-dev'

@description('Initial container image. GitHub Actions replaces it with an immutable ACR digest after deployment.')
param initialContainerImage string

@description('Immutable GitHub OIDC subject for the protected dev environment.')
param githubOidcSubject string

@description('Resource names for the dev environment.')
param names object

@description('Existing role-assignment names used when adopting the current dev environment.')
param roleAssignmentNames object = {}

var deployerRoleDefinitionName = '50eca956-3a91-43c3-ab49-972bc9212801'
var jobRunnerRoleDefinitionName = '103931b6-d031-4b5a-8e0e-2e5661c00019'

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
}

resource jobDeployerRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: deployerRoleDefinitionName
  properties: {
    roleName: 'TenderScope Container Apps Job Deployer'
    description: 'Update the TenderScope dev Container Apps Job without starting or deleting it or reading secrets.'
    type: 'CustomRole'
    assignableScopes: [
      subscription().id
    ]
    permissions: [
      {
        actions: [
          'Microsoft.App/jobs/read'
          'Microsoft.App/jobs/write'
          'Microsoft.App/jobs/executions/read'
        ]
        notActions: [
          'Microsoft.App/jobs/delete'
          'Microsoft.App/jobs/start/action'
          'Microsoft.App/jobs/listSecrets/action'
        ]
        dataActions: []
        notDataActions: []
      }
    ]
  }
}

resource jobRunnerRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: jobRunnerRoleDefinitionName
  properties: {
    roleName: 'TenderScope Container Apps Job Runner'
    description: 'Read and start only the TenderScope dev Container Apps Job and monitor its executions.'
    type: 'CustomRole'
    assignableScopes: [
      subscription().id
    ]
    permissions: [
      {
        actions: [
          'Microsoft.App/jobs/read'
          'Microsoft.App/jobs/start/action'
          'Microsoft.App/jobs/executions/read'
          'Microsoft.App/jobs/execution/read'
        ]
        notActions: []
        dataActions: []
        notDataActions: []
      }
    ]
  }
}

module platform './modules/platform.bicep' = {
  name: 'tenderscope-dev-platform'
  scope: resourceGroup
  params: {
    location: location
    initialContainerImage: initialContainerImage
    githubOidcSubject: githubOidcSubject
    jobDeployerRoleDefinitionId: jobDeployerRole.id
    jobRunnerRoleDefinitionId: jobRunnerRole.id
    names: names
    roleAssignmentNames: roleAssignmentNames
  }
}

output resourceGroupId string = resourceGroup.id
output containerAppJobName string = platform.outputs.containerAppJobName
output deploymentIdentityName string = platform.outputs.deploymentIdentityName
output runnerIdentityName string = platform.outputs.runnerIdentityName
output runtimeIdentityName string = platform.outputs.runtimeIdentityName
