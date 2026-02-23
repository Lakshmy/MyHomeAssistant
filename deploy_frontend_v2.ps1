# =============================================================================
# deploy_frontend_v2.ps1  —  Day-to-day frontend rebuild & redeploy for V2
#
# Reads the ACR from the currently-running Container App image tag, so no
# hardcoded registry names are needed.
# =============================================================================

$ResourceGroup   = "rg-assistant-v1"
$FrontendAppName = "app-assistant-frontend-v1"

# Derive ACR from the image currently running on the Container App
$CurrentImage = az containerapp show `
    --name $FrontendAppName `
    --resource-group $ResourceGroup `
    --query "properties.template.containers[0].image" -o tsv
$AcrServer = $CurrentImage.Split('/')[0]
$AcrName   = $AcrServer.Split('.')[0]

Write-Host "--------------------------------"
Write-Host "Building and pushing Frontend image..."
# Resolve the v2 backend URL so Vite bakes the correct API_URL at build time
$BackendFqdn = az containerapp show `
    --name "app-assistant-backend-v1" `
    --resource-group $ResourceGroup `
    --query "properties.configuration.ingress.fqdn" -o tsv
$ViteApiUrl = "https://$BackendFqdn"
Write-Host "VITE_API_URL=$ViteApiUrl"
# Build from repo root so the Dockerfile can access both infra/ and client/
az acr build --registry $AcrName --image "memory-frontend:latest" --file ./infra/client.Dockerfile --build-arg "VITE_API_URL=$ViteApiUrl" .

Write-Host "Updating Frontend Container App ($FrontendAppName)..."
$DeployTime = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
az containerapp update `
    --name $FrontendAppName `
    --resource-group $ResourceGroup `
    --image "$AcrServer/memory-frontend:latest" `
    --set-env-vars "DEPLOY_TIME=$DeployTime"

Write-Host "--------------------------------"
Write-Host "Frontend V2 Deployment Complete!"
Write-Host "Frontend URL: https://$(az containerapp show -n $FrontendAppName -g $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv)"
