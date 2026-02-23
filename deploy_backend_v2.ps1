# =============================================================================
# deploy_backend_v2.ps1  —  Day-to-day backend rebuild & redeploy for V2
#
# Reads all existing env vars from the running Container App so you do not
# need to re-supply secrets on every redeploy.
# =============================================================================

$ResourceGroup  = "rg-assistant-v1"
$BackendAppName = "app-assistant-backend-v1"

# Derive ACR from the image currently running on the Container App
$CurrentImage = az containerapp show `
    --name $BackendAppName `
    --resource-group $ResourceGroup `
    --query "properties.template.containers[0].image" -o tsv
$AcrServer = $CurrentImage.Split('/')[0]
$AcrName   = $AcrServer.Split('.')[0]

# Read current env vars from the running app so they are preserved
$GetEnv = { param($name)
    az containerapp show --name $BackendAppName --resource-group $ResourceGroup `
        --query "properties.template.containers[0].env[?name=='$name'].value" -o tsv
}

$StorageAccountUrl       = & $GetEnv "AZURE_STORAGE_ACCOUNT_URL"
$AzureOpenAiEndpoint     = & $GetEnv "AZURE_OPENAI_ENDPOINT"
$AzureOpenAiDeployment   = & $GetEnv "AZURE_OPENAI_DEPLOYMENT"
Write-Host "--------------------------------"
Write-Host "Building and pushing Backend image..."
az acr build --registry $AcrName --image "memory-backend:latest" ./server

Write-Host "Updating Backend Container App ($BackendAppName)..."
$RevisionSuffix = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
# API Key auth is disabled — no AZURE_OPENAI_API_KEY. Auth uses Managed Identity.
az containerapp update `
    --name $BackendAppName `
    --resource-group $ResourceGroup `
    --image "$AcrServer/memory-backend:latest" `
    --revision-suffix $RevisionSuffix `
    --set-env-vars `
        "AZURE_OPENAI_ENDPOINT=$AzureOpenAiEndpoint" `
        "AZURE_OPENAI_DEPLOYMENT=$AzureOpenAiDeployment" `
        "AZURE_STORAGE_ACCOUNT_URL=$StorageAccountUrl"

Write-Host "--------------------------------"
Write-Host "Backend V2 Deployment Complete!"
Write-Host "Backend URL: https://$(az containerapp show -n $BackendAppName -g $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv)"
