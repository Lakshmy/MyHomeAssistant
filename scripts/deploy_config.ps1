# Shared Azure deployment configuration
# Sourced by deploy.ps1, deploy_backend.ps1, deploy_frontend.ps1
# Auto-generated values are written by deploy_infra.ps1

function Assert-AzureLogin {
    $azAccount = az account show --query "user.name" -o tsv 2>$null
    if (-not $azAccount) {
        Write-Host "Not logged in. Run 'az login' first." -ForegroundColor Red
        throw "Azure CLI not logged in"
    }
    Write-Host "Logged in as: $azAccount" -ForegroundColor Green
}

function Assert-LastCommand {
    param([string]$Message = "Command failed")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: $Message (exit code $LASTEXITCODE)" -ForegroundColor Red
        throw $Message
    }
}

$ResourceGroup      = "rg-memory-assistant"
$Location           = "eastus"
$AcrName            = ""
$AcrServer          = ""
$BackendAppName     = "app-memory-backend"
$FrontendAppName    = "app-memory-frontend"
$StorageAccountName = ""
$StorageAccountUrl  = ""

# Load generated values if they exist
$generatedConfig = "$PSScriptRoot\deploy_config.generated.ps1"
if (Test-Path $generatedConfig) {
    . $generatedConfig
}

if (-not $AcrName -or -not $StorageAccountName) {
    Write-Host "Azure infrastructure not provisioned." -ForegroundColor Yellow
    $answer = Read-Host "Run infrastructure provisioning now? (y/n)"
    if ($answer -eq "y") {
        & "$PSScriptRoot\deploy_infra.ps1"
        if (Test-Path $generatedConfig) {
            . $generatedConfig
        }
        if (-not $AcrName -or -not $StorageAccountName) {
            throw "Infrastructure provisioning failed"
        }
    } else {
        Write-Host "Run .\scripts\deploy_infra.ps1 first to provision infrastructure." -ForegroundColor Gray
        throw "Infrastructure not provisioned"
    }
}

$AcrServer = "$AcrName.azurecr.io"
$StorageAccountUrl = "https://$StorageAccountName.blob.core.windows.net"
