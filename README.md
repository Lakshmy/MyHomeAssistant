# FindIt

A Progressive Web App (PWA) that helps elderly users locate household items using voice queries. Users upload walkthrough videos of their home; Google Gemini analyses the videos to build an inventory index of objects and locations. Users can then ask voice questions to find their belongings, and the app plays the relevant video clip alongside the answer.

> **Troubleshooting**: See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for a guide to common errors and fixes encountered during development.

---

## Architecture

![alt text](docs\arch.png)

## Technical Details

### Frontend Components

| Component | Technology | Purpose |
|---|---|---|
| UI Framework | React 18 + TypeScript | Component-based SPA |
| Build Tool | Vite | Fast dev build + production bundle |
| PWA | vite-plugin-pwa + Workbox | Installable app, offline caching |
| Routing | React Router v6 | Client-side navigation |
| Home (`App.tsx`) | React | Nav hub, Admin Mode toggle (persisted in localStorage) |
| Ask Question (`Chat.tsx`) | React | MediaRecorder API, voice recording, message display + video clip player |
| Upload Videos (`Record.tsx`) | React | Multi-stage upload flow with Gemini analysis spinner |
| My Videos (`Videos.tsx`) | React | Video list, inline player, per-video inventory index editor |
| Web Speech API | Browser native | Text-to-speech readback of assistant answers |
| Container | nginx:alpine | Serves the static Vite build |
| Registry | Azure Container Registry | Stores `memory-frontend:latest` image |
| Hosting | Azure Container Apps | `<your-frontend-app>` |

### Backend Components

| Component | Technology | Purpose |
|---|---|---|
| API Framework | FastAPI (Python 3.11) | REST API, async request handling |
| AI | Google Gemini (`gemini-3-flash-preview`) | Audio transcription + inventory Q&A; video item extraction |
| Storage SDK | `azure-storage-blob` | Upload, list, stream, delete blobs |
| Auth | `azure-identity` — `ManagedIdentityCredential` / `AzureCliCredential` | Passwordless auth to Azure Storage (Managed Identity in Azure, `az login` locally) |
| RBAC Role | Storage Blob Data Contributor | Grants backend read/write on the blob container |
| Blob: Video | `{uuid}_{filename}` | Raw uploaded video file |
| Blob: Index | `{uuid}_{filename}.index.json` | AI-extracted item inventory (object, location, room, notes, timestamp_start) |
| Video Streaming | HTTP Range requests (`206 Partial Content`) | Efficient in-browser video playback |
| Container | Python 3.11 slim | Runtime image |
| Registry | Azure Container Registry | Stores `memory-backend:latest` image |
| Hosting | Azure Container Apps | `<your-backend-app>` with System-Assigned Managed Identity |

### Backend API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat-audio` | Accepts audio file; transcribes with Gemini; looks up inventory; returns answer + matched video name |
| `POST` | `/analyze-video` | Uploads video to blob storage; runs Gemini analysis; saves `.index.json` companion blob |
| `GET` | `/videos` | Lists all videos with size, last modified, and `has_index` flag |
| `GET` | `/videos/{name}/stream` | HTTP range-aware video streaming from blob storage |
| `GET` | `/videos/{name}/index` | Returns the inventory index JSON for a specific video |
| `PUT` | `/videos/{name}/index` | Overwrites the inventory index JSON (admin edit) |
| `DELETE` | `/videos/{name}` | Deletes the video blob and its companion `.index.json` |

### Azure Resources

| Resource | Name |
|---|---|
| Resource Group | `<your-resource-group>` |
| Container Registry | `<your-acr-name>` |
| Storage Account | `<your-storage-account>` |
| Blob Container | `user-videos` |
| Frontend App | `<your-frontend-app>` |
| Backend App | `<your-backend-app>` |
| Region | East US |

---

## Configuration

These settings are required for both local development and Azure deployment.

### Google Gemini API Key

1. Get your API key from [Google AI Studio](https://aistudio.google.com/).

> **Note**: The free tier of the Gemini API has a limit of ~20 requests/day. Enable billing in Google AI Studio for production use.

### Azure Storage Access

The backend uses **passwordless auth** (no connection strings). It auto-detects the environment:

| Environment | Credential | How it works |
|---|---|---|
| Azure Container Apps | `ManagedIdentityCredential` | Backend's System-Assigned Managed Identity — automatic, no config needed |
| Local development | `AzureCliCredential` | Uses your `az login` session |

Both environments require the **Storage Blob Data Contributor** RBAC role on the storage account. Ensure `publicNetworkAccess` is **Enabled** on the storage account.

---

## Local Development

Follow these steps to run the app on your machine for testing or development.

### Prerequisites

| Requirement | Purpose |
|---|---|
| **Python 3.11+** | Backend runtime |
| **Node.js 18+** | Frontend dev server (Vite) |
| **Azure CLI** | Auth to Azure Blob Storage via `az login` |
| **Google Gemini API Key** | AI transcription and inventory extraction (see [Configuration](#google-gemini-api-key)) |

### Step 1 — Configure Environment

Copy the template and fill in your values:

```powershell
copy server\.env.example server\.env
```

Edit `server\.env`:

```env
GOOGLE_API_KEY=<your-gemini-api-key>
AZURE_STORAGE_ACCOUNT_URL=https://<your-storage-account>.blob.core.windows.net
```

> If you already have an Azure deployment, you can retrieve these values:
> ```powershell
> az containerapp show --name <your-backend-app> --resource-group <your-resource-group> `
>   --query "properties.template.containers[0].env[?name=='GOOGLE_API_KEY'].value" -o tsv
>
> az containerapp show --name <your-backend-app> --resource-group <your-resource-group> `
>   --query "properties.template.containers[0].env[?name=='AZURE_STORAGE_ACCOUNT_URL'].value" -o tsv
> ```

The frontend is pre-configured — `client\.env.local` points to `http://localhost:8000`. When absent, the frontend falls back to the Azure backend URL hardcoded in the source.

### Step 2 — Grant Storage Access

Log in to Azure and assign the required RBAC role to your user:

```powershell
az login

# Get your user's Object ID
$userId = az ad signed-in-user show --query id -o tsv

# Get the storage account resource ID
$storageId = az storage account show --name <your-storage-account> `
  --resource-group <your-resource-group> --query id -o tsv

# Assign the role
az role assignment create --assignee $userId `
  --role "Storage Blob Data Contributor" --scope $storageId
```

> RBAC propagation can take up to 5 minutes. Restart the backend after assigning the role.

### Step 3 — Start the App

```powershell
.\scripts\start_local.ps1
```

The script will:
1. Check prerequisites (Python, Node.js, Azure CLI login, `.env` file)
2. Install dependencies if needed (`npm install`, `pip install`)
3. Open two terminal windows — backend and frontend
4. Wait until both servers are listening

Once ready:
- **Backend** → http://localhost:8000
- **Frontend** → http://localhost:5173

> **Note**: The backend takes ~30 seconds to start while it fetches an Azure credential token. Wait for `Uvicorn running on http://0.0.0.0:8000` in the backend terminal.

### Stopping the App

```powershell
.\scripts\stop_local.ps1
```

### Manual Start (alternative)

If you prefer to start the servers yourself instead of using the script:

```powershell
# Terminal 1 — Backend
cd server
pip install -r requirements.txt    # First time only
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd client
npm install                         # First time only
npx vite --host
```

---

## Azure Deployment (Production)

Follow these steps to deploy the app to Azure Container Apps.

### Prerequisites

- Azure CLI logged in (`az login`)
- Google Gemini API Key (see [Configuration](#google-gemini-api-key))
- No local Docker required — builds run in Azure Container Registry (cloud build)

### Step 1 — Provision Infrastructure (first time only)

This creates the resource group, storage account, container registry, container apps, managed identity, and RBAC roles:

```powershell
.\scripts\deploy_infra.ps1
```

The script deploys the Bicep template (`infra/main.bicep`) and saves the generated resource names to `scripts/deploy_config.generated.ps1` (gitignored). You only need to run this once.

### Step 2 — Deploy the App

```powershell
# Full deploy (frontend + backend)
.\scripts\deploy.ps1
```

Or deploy individually after making changes:

```powershell
.\scripts\deploy_backend.ps1    # After API/backend changes
.\scripts\deploy_frontend.ps1   # After UI/frontend changes
```

The deploy scripts will:
1. Verify Azure CLI login and load resource names from the generated config
2. Build container images in ACR (cloud build — no local Docker needed)
3. Update the Container Apps with the new images
4. Print the live URLs when complete

### Step 3 — Set the Gemini API Key

On first deployment, set the API key on the backend:

```powershell
az containerapp update `
  --name app-memory-backend `
  --resource-group rg-memory-assistant `
  --set-env-vars GOOGLE_API_KEY=<your-gemini-api-key>
```

### Teardown

To delete the Azure deployment:

```powershell
.\scripts\teardown_azure.ps1
```

You'll be prompted to choose:
1. **Delete Container Apps only** — removes the running apps but keeps your storage account, container registry, and all uploaded videos/data
2. **Delete entire resource group** — permanently removes **everything** (apps, storage, registry, all data). Requires typing the resource group name to confirm

---

## Scripts Overview

All operations are available through the interactive launcher:

```powershell
.\run.ps1
```

```
========================================
   FindIt - Launcher
========================================

  1) Provision Azure infrastructure (first time)
  2) Deploy to Azure (full)
  3) Deploy backend only (Azure)
  4) Deploy frontend only (Azure)
  5) Start local servers
  6) Stop local servers
  7) Teardown Azure deployment
  0) Exit
```

| Script | Purpose |
|---|---|
| `run.ps1` | **Interactive launcher** — menu for all operations |
| `scripts/start_local.ps1` | Start local dev servers with prerequisite checks |
| `scripts/stop_local.ps1` | Stop locally running servers |
| `scripts/deploy_infra.ps1` | Provision Azure infrastructure (resource group, ACR, storage, apps) |
| `scripts/deploy.ps1` | Deploy both frontend and backend to Azure |
| `scripts/deploy_backend.ps1` | Deploy backend only to Azure |
| `scripts/deploy_frontend.ps1` | Deploy frontend only to Azure |
| `scripts/deploy_config.ps1` | Shared Azure config (sourced automatically by deploy scripts) |
| `scripts/teardown_azure.ps1` | Delete Azure deployment (Container Apps only or full resource group) |

---

## Usage

1. Enable **Admin Mode** on the home screen (toggle top-right).
2. Tap **Upload Videos** — select one or more walkthrough videos of your home.
3. The app uploads each video and runs AI analysis to extract an inventory of objects and their locations.
4. Tap **My Videos** to view, play, and edit the extracted inventory for each video.
5. Tap **Ask Question** — allow microphone access, then tap **Tap to Speak**.
6. Ask where something is (e.g. *"Where are my glasses?"*).
7. Tap **Stop & Send** — the app responds with the location and plays the relevant video clip.
