# Tear down Azure deployment for FindIt
# Usage: .\teardown_azure.ps1

$ResourceGroup   = "rg-memory-assistant"
$BackendAppName  = "app-memory-backend"
$FrontendAppName = "app-memory-frontend"

# Check Azure CLI login
$azAccount = az account show --query "user.name" -o tsv 2>$null
if (-not $azAccount) {
    Write-Host "Not logged in. Run 'az login' first." -ForegroundColor Red
    exit 1
}
Write-Host "Logged in as: $azAccount" -ForegroundColor Green

Write-Host ""
Write-Host "=== FindIt - Azure Teardown ===" -ForegroundColor Red
Write-Host ""
Write-Host "  1) Delete Container Apps only (keeps storage, ACR, and data)" -ForegroundColor White
Write-Host "  2) Delete entire resource group (removes EVERYTHING)" -ForegroundColor White
Write-Host "  0) Cancel" -ForegroundColor Gray
Write-Host ""

$choice = Read-Host "Select an option"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "Deleting Container Apps..." -ForegroundColor Yellow

        Write-Host "  Deleting frontend: $FrontendAppName"
        az containerapp delete --name $FrontendAppName --resource-group $ResourceGroup --yes

        Write-Host "  Deleting backend: $BackendAppName"
        az containerapp delete --name $BackendAppName --resource-group $ResourceGroup --yes

        Write-Host ""
        Write-Host "Container Apps deleted. Storage account and ACR are still intact." -ForegroundColor Green
    }
    "2" {
        Write-Host ""
        Write-Host "WARNING: This will permanently delete:" -ForegroundColor Red
        Write-Host "  - Resource Group: $ResourceGroup" -ForegroundColor Red
        Write-Host "  - All Container Apps, Container Registry, Storage Account" -ForegroundColor Red
        Write-Host "  - All uploaded videos and inventory data" -ForegroundColor Red
        Write-Host ""

        $confirm = Read-Host "Type the resource group name to confirm ($ResourceGroup)"
        if ($confirm -eq $ResourceGroup) {
            Write-Host ""
            Write-Host "Deleting resource group '$ResourceGroup'... (this may take a few minutes)" -ForegroundColor Yellow
            az group delete --name $ResourceGroup --yes --no-wait
            # Remove generated config since resources are gone
            $genConfig = "$PSScriptRoot\deploy_config.generated.ps1"
            if (Test-Path $genConfig) { Remove-Item $genConfig }
            Write-Host "Resource group deletion initiated." -ForegroundColor Green
            Write-Host "Run 'az group show -n $ResourceGroup' to check status." -ForegroundColor Gray
        } else {
            Write-Host "Confirmation did not match. Cancelled." -ForegroundColor Yellow
        }
    }
    "0" {
        Write-Host "Cancelled." -ForegroundColor Gray
    }
    default {
        Write-Host "Invalid option." -ForegroundColor Red
    }
}
