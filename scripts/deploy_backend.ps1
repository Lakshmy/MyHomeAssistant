$ErrorActionPreference = "Stop"

# Load shared config (throws if infra not provisioned)
. "$PSScriptRoot\deploy_config.ps1"

# Switch to Continue so az CLI stderr warnings don't terminate the script
$ErrorActionPreference = "Continue"

# Ensure we run from the project root
Push-Location "$PSScriptRoot\.."

Assert-AzureLogin

# Backend Build & Push (Using Azure Cloud Build - no local Docker required)
Write-Host "--------------------------------"
Write-Host "Building and Pushing Backend Image to ACR..."
az acr build --registry $AcrName --image "memory-backend:latest" ./server 2>$null
Assert-LastCommand "Backend image build failed"

# Get Existing Google API Key from running container
$GoogleApiKey = az containerapp show --name $BackendAppName --resource-group $ResourceGroup --query "properties.template.containers[0].env[?name=='GOOGLE_API_KEY'].value" -o tsv 2>$null

Write-Host "Updating Backend Container App (with Google Key & Storage)..."
az containerapp update --name $BackendAppName --resource-group $ResourceGroup `
    --image "$AcrServer/memory-backend:latest" `
    --set-env-vars "GOOGLE_API_KEY=$GoogleApiKey" "AZURE_STORAGE_ACCOUNT_URL=$StorageAccountUrl" 2>$null
Assert-LastCommand "Backend update failed"

Write-Host "--------------------------------"
Write-Host "Backend Deployment Complete!" -ForegroundColor Green
Write-Host "Backend URL: https://$(az containerapp show -n $BackendAppName -g $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv)"
Pop-Location
