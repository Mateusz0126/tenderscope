targetScope = 'resourceGroup'

@description('Monthly cost amount in the subscription billing currency.')
@minValue(1)
param monthlyBudgetAmount int = 15

@description('Email that receives budget notifications. Supply at deployment time; never commit it.')
@secure()
param notificationEmail string

@description('First day of the current month in ISO 8601 format.')
param budgetStartDate string = utcNow('yyyy-MM-01T00:00:00Z')

@description('Name of the resource-group budget.')
param budgetName string = 'budget-tenderscope-dev'

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: budgetName
  properties: {
    amount: monthlyBudgetAmount
    category: 'Cost'
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: budgetStartDate
    }
    notifications: {
      Actual50Percent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: [
          notificationEmail
        ]
        contactGroups: []
        contactRoles: []
        locale: 'pl-pl'
      }
      Actual80Percent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [
          notificationEmail
        ]
        contactGroups: []
        contactRoles: []
        locale: 'pl-pl'
      }
      Actual100Percent: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [
          notificationEmail
        ]
        contactGroups: []
        contactRoles: []
        locale: 'pl-pl'
      }
    }
  }
}

output budgetResourceId string = budget.id
