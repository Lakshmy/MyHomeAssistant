param location string = resourceGroup().location
param environmentName string = 'env-memory-assistant'
param containerRegistryName string = 'acr${uniqueString(resourceGroup().id)}'
param backendAppName string = 'app-memory-backend'
param frontendAppName string = 'app-memory-frontend'

// 1. Container Registry
resource acr 'Microsoft.ContainerRegistry/registries@2023-01-01-preview' = {
  name: containerRegistryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// 2. Container Apps Environment
resource env 'Microsoft.App/managedEnvironments@2022-11-01-preview' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'log-${environmentName}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// 3. Backend Container App (Placeholder image initially)
resource backendApp 'Microsoft.App/containerApps@2022-11-01-preview' = {
  name: backendAppName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
      ]
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.properties.adminUserEnabled ? acr.name : ''
          passwordSecretRef: 'acr-password'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'memory-backend'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' // Replace with your ACR image later
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 10
      }
    }
  }
}

// 4. Frontend Container App (Placeholder image initially)
resource frontendApp 'Microsoft.App/containerApps@2022-11-01-preview' = {
  name: frontendAppName
  location: location
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: {
        external: true
        targetPort: 80
        transport: 'auto'
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.properties.adminUserEnabled ? acr.name : ''
          passwordSecretRef: 'acr-password' // Assuming same credentials usage
        }
      ]
      secrets: [
         {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'memory-frontend'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' // Replace with your ACR image later
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 10
      }
    }
  }
}

output acrLoginServer string = acr.properties.loginServer
output backendUrl string = backendApp.properties.configuration.ingress.fqdn
output frontendUrl string = frontendApp.properties.configuration.ingress.fqdn
output backendPrincipalId string = backendApp.identity.principalId
