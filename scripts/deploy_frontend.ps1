$ErrorActionPreference = "Stop"

# Load shared config (throws if infra not provisioned)
. "$PSScriptRoot\deploy_config.ps1"

# Switch to Continue so az CLI stderr warnings don't terminate the script
$ErrorActionPreference = "Continue"

# Ensure we run from the project root
Push-Location "$PSScriptRoot\.."

Assert-AzureLogin

# Frontend Build & Push (Using Azure Cloud Build - no local Docker required)
Write-Host "--------------------------------"
Write-Host "Building and Pushing Frontend Image to ACR..."
az acr build --registry $AcrName --image "memory-frontend:latest" --file ./infra/client.Dockerfile . 2>$null
Assert-LastCommand "Frontend image build failed"

Write-Host "Updating Frontend Container App..."
$DeployTime = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
az containerapp update --name $FrontendAppName --resource-group $ResourceGroup `
    --image "$AcrServer/memory-frontend:latest" `
    --set-env-vars "DEPLOY_TIME=$DeployTime" 2>$null
Assert-LastCommand "Frontend update failed"

Write-Host "--------------------------------"
Write-Host "Frontend Deployment Complete!" -ForegroundColor Green
Write-Host "Frontend URL: https://$(az containerapp show -n $FrontendAppName -g $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv)"
Pop-Location
