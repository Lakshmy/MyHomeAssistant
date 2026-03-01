$ErrorActionPreference = "Stop"

# Load shared config (throws if infra not provisioned)
. "$PSScriptRoot\deploy_config.ps1"

# Switch to Continue so az CLI stderr warnings don't terminate the script
$ErrorActionPreference = "Continue"

# Ensure we run from the project root
Push-Location "$PSScriptRoot\.."

Write-Host "Checking Azure CLI login..."
Assert-AzureLogin

# 1. Backend Build & Push (Using Azure Cloud Build)
Write-Host "--------------------------------"
Write-Host "Building and Pushing Backend Image to ACR..."
az acr build --registry $AcrName --image "memory-backend:latest" ./server 2>$null
Assert-LastCommand "Backend image build failed"

# Get Existing Google API Key from running container
$GoogleApiKey = az containerapp show --name $BackendAppName --resource-group $ResourceGroup --query "properties.template.containers[0].env[?name=='GOOGLE_API_KEY'].value" -o tsv 2>$null

# Fall back to server/.env if key is empty (e.g. first deploy after provisioning)
if (-not $GoogleApiKey) {
    $envFile = "$PSScriptRoot\..\server\.env"
    if (Test-Path $envFile) {
        $match = Select-String -Path $envFile -Pattern "^GOOGLE_API_KEY=(.+)" | Select-Object -First 1
        if ($match) {
            $GoogleApiKey = $match.Matches[0].Groups[1].Value.Trim()
            Write-Host "GOOGLE_API_KEY loaded from server\.env" -ForegroundColor Yellow
        }
    }
}
if (-not $GoogleApiKey) {
    Write-Host "WARNING: GOOGLE_API_KEY is not set. Gemini features will not work." -ForegroundColor Red
    Write-Host "Set it in server\.env and re-deploy, or update the container app manually." -ForegroundColor Red
}

Write-Host "Updating Backend Container App (with Google Key & Storage)..."
az containerapp update --name $BackendAppName --resource-group $ResourceGroup `
    --image "$AcrServer/memory-backend:latest" `
    --set-env-vars "GOOGLE_API_KEY=$GoogleApiKey" "AZURE_STORAGE_ACCOUNT_URL=$StorageAccountUrl" 2>$null
Assert-LastCommand "Backend update failed"

# 3. Frontend Build & Push (Using Azure Cloud Build)
# Dynamically resolve backend URL so frontend always points to the current backend
$BackendFqdn = az containerapp show -n $BackendAppName -g $ResourceGroup --query "properties.configuration.ingress.fqdn" -o tsv 2>$null
$BackendApiUrl = "https://$BackendFqdn"
Write-Host "Frontend will use backend: $BackendApiUrl"
Write-Host "--------------------------------"
Write-Host "Building and Pushing Frontend Image to ACR..."
az acr build --registry $AcrName --image "memory-frontend:latest" --file ./infra/client.Dockerfile --build-arg "VITE_API_URL=$BackendApiUrl" . 2>$null
Assert-LastCommand "Frontend image build failed"

Write-Host "Updating Frontend Container App..."
$DeployTime = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
az containerapp update --name $FrontendAppName --resource-group $ResourceGroup --image "$AcrServer/memory-frontend:latest" --set-env-vars "DEPLOY_TIME=$DeployTime" 2>$null
Assert-LastCommand "Frontend update failed"

Write-Host "--------------------------------"
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "Backend URL: https://$(az containerapp show -n $BackendAppName -g $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv)"
Write-Host "Frontend URL: https://$(az containerapp show -n $FrontendAppName -g $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv)"
Pop-Location
