# =============================================================================
# deploy_v2.ps1  —  Full first-time deployment for the GPT-5.2 / V2 environment
#
# Prerequisites (set these as environment variables before running):
#   $env:AZURE_OPENAI_ENDPOINT      = "https://<your-foundry-resource>.services.ai.azure.com"
#   $env:AZURE_OPENAI_DEPLOYMENT    = "gpt-5.2"   # defaults to "gpt-5.2" if not set
#   $env:AZURE_WHISPER_DEPLOYMENT   = "whisper"   # defaults to "whisper" if not set
#
# Auth uses Managed Identity (production) or 'az login' (local dev).
#
# This script:
#   1. Creates resource group rg-memory-assistant-v2
#   2. Deploys Bicep (new ACR, Container Apps env, backend + frontend apps)
#   3. Creates a new Azure Storage account
#   4. Assigns Storage Blob Data Contributor to the backend Managed Identity
#   5. Builds & pushes backend + frontend images to the new ACR
#   6. Updates both Container Apps with the correct env vars
# =============================================================================

$ResourceGroup    = "rg-assistant-v1"
$Location         = "swedencentral"
$EnvName          = "env-assistant-v1"
$BackendAppName   = "app-assistant-backend-v1"
$FrontendAppName  = "app-assistant-frontend-v1"

# ── 1. Ensure resource group exists ───────────────────────────────────────────
Write-Host "Ensuring resource group: $ResourceGroup ..."
az group create --name $ResourceGroup --location $Location

# ── 2. Deploy Bicep infra (ACR, Container Apps env, backend + frontend apps) ──
Write-Host "Deploying infrastructure via Bicep..."
$BicepOutputJson = az deployment group create `
    --resource-group $ResourceGroup `
    --template-file ./infra/main.bicep `
    --parameters environmentName=$EnvName backendAppName=$BackendAppName frontendAppName=$FrontendAppName `
    --output json

$BicepOutput = $BicepOutputJson | ConvertFrom-Json
$AcrServer          = $BicepOutput.properties.outputs.acrLoginServer.value
$AcrName            = $AcrServer.Split('.')[0]
$BackendPrincipalId = $BicepOutput.properties.outputs.backendPrincipalId.value
Write-Host "ACR Login Server : $AcrServer"
Write-Host "Backend MI PID   : $BackendPrincipalId"

# ── 3. Create Storage Account ──────────────────────────────────────────────────
$StorageAccountName = "stmemv2" + $AcrName.Substring(3, [Math]::Min(5, $AcrName.Length - 3))
Write-Host "Checking Storage Account ($StorageAccountName)..."
$StorageExists = az storage account check-name --name $StorageAccountName --query "nameAvailable" -o tsv
if ($StorageExists -eq "true") {
    Write-Host "Creating Storage Account: $StorageAccountName"
    az storage account create `
        --name $StorageAccountName `
        --resource-group $ResourceGroup `
        --location $Location `
        --sku Standard_LRS
} else {
    Write-Host "Storage Account already exists."
}
$StorageAccountUrl  = "https://$StorageAccountName.blob.core.windows.net"
$StorageResourceId  = az storage account show --name $StorageAccountName --resource-group $ResourceGroup --query "id" -o tsv

# ── 4. Assign Storage Blob Data Contributor to backend Managed Identity ────────
Write-Host "Assigning 'Storage Blob Data Contributor' to backend identity ($BackendPrincipalId)..."
az role assignment create `
    --assignee $BackendPrincipalId `
    --role "Storage Blob Data Contributor" `
    --scope $StorageResourceId

# ── 5. Build and push images (no local Docker needed — ACR cloud build) ────────
Write-Host "Building and pushing Backend image..."
az acr build --registry $AcrName --image "memory-backend:latest" ./server

Write-Host "Building and pushing Frontend image..."
$BackendFqdn = az containerapp show --name $BackendAppName --resource-group $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv
az acr build --registry $AcrName --image "memory-frontend:latest" --file ./infra/client.Dockerfile --build-arg "VITE_API_URL=https://$BackendFqdn" .

# ── 6. Resolve Azure OpenAI settings from env vars ────────────────────────────
# API Key auth is disabled on the Foundry resource. The backend uses Managed Identity.
$AzureOpenAiEndpoint   = $env:AZURE_OPENAI_ENDPOINT
$AzureOpenAiDeployment = if ($env:AZURE_OPENAI_DEPLOYMENT) { $env:AZURE_OPENAI_DEPLOYMENT } else { "gpt-5.2" }

if (-not $AzureOpenAiEndpoint) {
    Write-Warning "AZURE_OPENAI_ENDPOINT is not set. Backend will start but AI calls will fail until it is configured."
}

# ── 6b. Assign 'Cognitive Services OpenAI User' to backend MI on the Foundry resource
# Requires $env:AZURE_AI_RESOURCE_ID — the resource ID of your Azure AI Foundry account.
# Get it from: az cognitiveservices account show -n <name> -g <rg> --query id -o tsv
if ($env:AZURE_AI_RESOURCE_ID) {
    Write-Host "Assigning 'Cognitive Services OpenAI User' to backend identity on AI resource..."
    az role assignment create `
        --assignee $BackendPrincipalId `
        --role "Cognitive Services OpenAI User" `
        --scope $env:AZURE_AI_RESOURCE_ID
} else {
    Write-Warning "AZURE_AI_RESOURCE_ID not set — skipping OpenAI RBAC assignment."
    Write-Warning "Manually assign 'Cognitive Services OpenAI User' to the backend Managed Identity ($BackendPrincipalId) on your AI Foundry resource."
}

# ── 7. Update Backend Container App ───────────────────────────────────────────
Write-Host "Updating Backend Container App ($BackendAppName)..."
az containerapp update `
    --name $BackendAppName `
    --resource-group $ResourceGroup `
    --image "$AcrServer/memory-backend:latest" `
    --set-env-vars `
        "AZURE_OPENAI_ENDPOINT=$AzureOpenAiEndpoint" `
        "AZURE_OPENAI_DEPLOYMENT=$AzureOpenAiDeployment" `
        "AZURE_STORAGE_ACCOUNT_URL=$StorageAccountUrl"

# ── 8. Update Frontend Container App ──────────────────────────────────────────
Write-Host "Updating Frontend Container App ($FrontendAppName)..."
$DeployTime = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
az containerapp update `
    --name $FrontendAppName `
    --resource-group $ResourceGroup `
    --image "$AcrServer/memory-frontend:latest" `
    --set-env-vars "DEPLOY_TIME=$DeployTime"

# ── Summary ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "================================ V2 Deployment Complete ================================"
Write-Host "Backend  URL : https://$(az containerapp show -n $BackendAppName  -g $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv)"
Write-Host "Frontend URL : https://$(az containerapp show -n $FrontendAppName -g $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv)"
Write-Host "  az containerapp update -n $BackendAppName -g $ResourceGroup --set-env-vars 'AI_PROVIDER=azure_openai'"
