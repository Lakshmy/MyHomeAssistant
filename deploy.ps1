$ResourceGroup = "rg-memory-assistant"
$AcrName = "acrjz2jhmcdr5d34" 
$AcrServer = "$AcrName.azurecr.io"
$BackendAppName = "app-memory-backend"
$FrontendAppName = "app-memory-frontend"
$StorageAccountName = "stmem" + $AcrName.Substring(3, 5) # Generate unique storage name

# 1. Login to Azure (if not already) and ACR
Write-Host "Logging into ACR ($AcrServer)..."
az acr login --name $AcrName

# 1b. Ensure Storage Account Exists
Write-Host "Checking Storage Account ($StorageAccountName)..."
$StorageExists = az storage account check-name --name $StorageAccountName --query "nameAvailable" -o tsv
if ($StorageExists -eq "true") {
    Write-Host "Creating Storage Account: $StorageAccountName"
    az storage account create --name $StorageAccountName --resource-group $ResourceGroup --location eastus --sku Standard_LRS
} else {
    Write-Host "Storage Account already exists (or name taken)."
}

# Build Storage Account URL (used with Managed Identity - no connection string needed)
$StorageAccountUrl = "https://$StorageAccountName.blob.core.windows.net"

# 2. Backend Build & Push (Using Azure Cloud Build)
Write-Host "--------------------------------"
Write-Host "Building and Pushing Backend Image to ACR..."
az acr build --registry $AcrName --image "memory-backend:latest" ./server

# Get Existing Google API Key
$GoogleApiKey = az containerapp show --name $BackendAppName --resource-group $ResourceGroup --query "properties.template.containers[0].env[?name=='GOOGLE_API_KEY'].value" -o tsv

Write-Host "Updating Backend Container App (with Google Key & Storage)..."
az containerapp update --name $BackendAppName --resource-group $ResourceGroup `
    --image "$AcrServer/memory-backend:latest" `
    --set-env-vars "GOOGLE_API_KEY=$GoogleApiKey" "AZURE_STORAGE_ACCOUNT_URL=$StorageAccountUrl"

# 3. Frontend Build & Push (Using Azure Cloud Build)
Write-Host "--------------------------------"
Write-Host "Building and Pushing Frontend Image to ACR..."
# Note: Building from root context to access infra/ and client/ folders
az acr build --registry $AcrName --image "memory-frontend:latest" --file ./infra/client.Dockerfile .

Write-Host "Updating Frontend Container App..."
$DeployTime = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
az containerapp update --name $FrontendAppName --resource-group $ResourceGroup --image "$AcrServer/memory-frontend:latest" --set-env-vars "DEPLOY_TIME=$DeployTime"

Write-Host "--------------------------------"
Write-Host "Deployment Complete!"
Write-Host "Backend URL: https://$(az containerapp show -n $BackendAppName -g $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv)"
Write-Host "Frontend URL: https://$(az containerapp show -n $FrontendAppName -g $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv)"
