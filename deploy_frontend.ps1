$ResourceGroup = "rg-memory-assistant"
$AcrName = "acrjz2jhmcdr5d34" 
$AcrServer = "$AcrName.azurecr.io"
$FrontendAppName = "app-memory-frontend"

# Login to ACR (Cloud-side)
# Write-Host "Logging into ACR ($AcrServer)..."
# az acr login --name $AcrName

# 3. Frontend Build & Push (Using Azure Cloud Build)
Write-Host "--------------------------------"
Write-Host "Building and Pushing Frontend Image to ACR..."
# Note: Building from root context to access infra/ and client/ folders
az acr build --registry $AcrName --image "memory-frontend:latest" --file ./infra/client.Dockerfile .

Write-Host "Updating Frontend Container App..."
az containerapp update --name $FrontendAppName --resource-group $ResourceGroup --image "$AcrServer/memory-frontend:latest"

Write-Host "--------------------------------"
Write-Host "Frontend Deployment Complete!"
Write-Host "Frontend URL: https://$(az containerapp show -n $FrontendAppName -g $ResourceGroup --query 'properties.configuration.ingress.fqdn' -o tsv)"
