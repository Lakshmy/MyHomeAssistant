# Troubleshooting Guide — Memory Assistant PWA

A record of real issues encountered during development and how each was diagnosed and fixed.

---

## 1. My Videos page — "Failed to fetch"

**Symptom**  
Clicking "My Videos" shows `Failed to fetch` in the UI. The `/videos` backend endpoint returns `500 Internal Server Error`.

**Diagnosis**  
Backend logs showed:
```
ErrorCode:AuthorizationFailure
This request is not authorized to perform this operation.
```
Checking the storage account revealed:
```json
"publicNetworkAccess": "Disabled"
```

**Root Cause**  
Azure Container Apps are **not** in the Azure Storage "trusted Azure services" bypass list. When `publicNetworkAccess` is `Disabled`, all requests from Container Apps are blocked at the network level — even if the Managed Identity has the correct RBAC role. Azure reports this as `AuthorizationFailure` rather than a network error, which makes it misleading.

**Fix**  
Re-enable public network access on the storage account:
```powershell
az storage account update \
  --name <your-storage-account> \
  --resource-group <your-resource-group> \
  --public-network-access Enabled
```

Security is still enforced via Managed Identity + RBAC (`allowSharedKeyAccess` remains `false`).

**Check RBAC assignment too**  
If the Container App was re-created, its System-Assigned Managed Identity gets a new Principal ID. Verify it matches the role assignment:
```powershell
# Get current backend identity
az containerapp show --name <your-backend-app> --resource-group <your-resource-group> --query "identity.principalId" -o tsv

# List role assignments on storage
$storageId = az storage account show --name <your-storage-account> --resource-group <your-resource-group> --query id -o tsv
az role assignment list --scope $storageId --output table
```
If the Principal IDs don't match, reassign the role:
```powershell
az role assignment create \
  --assignee "<principalId>" \
  --role "Storage Blob Data Contributor" \
  --scope $storageId
```

---

## 2. Google Gemini 429 — Quota Exhausted

**Symptom**  
All API calls return:  
`"I'm sorry, I'm having trouble connecting to the AI service right now. Please try again later."`

**Diagnosis**  
Backend logs showed:
```
429 RESOURCE_EXHAUSTED
Quota exceeded for metric: generate_content_free_tier_requests
limit: 20, model: gemini-2.5-flash-lite
```

**Root Cause**  
The free tier of `gemini-flash-lite-latest` (which resolves to `gemini-2.5-flash-lite`) allows only **20 requests per day**. Switching to `gemini-2.0-flash` made it worse — that model has an even lower free tier limit and was being called **twice per request** (transcription + answer as two separate calls).

**Fix — Short term**  
Wait for quota to reset at midnight UTC. Switch back to a single-call approach with `gemini-flash-lite-latest`:
```python
model_name = "gemini-flash-lite-latest"
```

**Fix — Long term (production)**  
Enable billing on your Google AI Studio project:
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Select your project → **Enable billing**

This increases limits from 20 req/day to 1,000+ RPM.

**Lesson learned**  
Avoid multi-step Gemini calls (e.g. separate transcription + answer steps) during development — they burn through free tier quota quickly. Combine into a single call with a combined prompt.

---

## 3. AI not answering general knowledge questions

**Symptom**  
Asking "What is the capital of Finland?" returned:  
`"I cannot help you with general knowledge questions. I can only help you find items listed in the inventory index."`

**Diagnosis**  
The multimodal Gemini model (audio + text combined call) was overriding the prompt instructions with its built-in safety/scope training. No matter how the system prompt was written, the model refused non-inventory questions when processing audio+text together.

**Attempts that did NOT work**  
- Adding `"You MUST answer ALL questions"` to the user prompt — model ignored it  
- Using `GenerateContentConfig(system_instruction=...)` — still overridden by multimodal pathway  
- Two-step approach (separate transcription + answer calls) — burned quota and still failed  

**Final decision**  
Scope the app to **inventory-only** responses with explicit response templates:

```python
prompt = (
    "RULE 1 — If asking where an item is located: search the INVENTORY INDEX. "
    "If found: give exact location. If NOT found: reply 'Sorry, I could not find [item] in the videos.' "
    "RULE 2 — If NOT about finding an item: reply 'Sorry, I don't know the answer to that.' "
    "Return JSON: {\"transcription\": \"...\", \"answer\": \"...\", \"video_id\": N_or_null}"
)
```

Using exact response templates prevents the model from improvising refusals.

---

## 4. Deploy script — Unicode encode error in terminal

**Symptom**  
After a successful deploy, the terminal shows:
```
ERROR: 'charmap' codec can't encode character '\u2713' in position 17
UnicodeEncodeError: 'charmap' codec can't encode character
```

**Root Cause**  
The Azure CLI outputs Unicode characters (e.g. `✓`) in its JSON response. PowerShell's default `cmd` code page (`cp1252`) cannot display them.

**This is NOT a real error** — the deployment always succeeded when this appeared. The `Deployment Complete!` message always appeared before it.

**Fix (cosmetic only)**  
To suppress the warning, run this in PowerShell before the deploy:
```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

Or verify deployment via timestamp instead of terminal output:
```powershell
az containerapp show --name <your-backend-app> --resource-group <your-resource-group> --query "systemData.lastModifiedAt" -o tsv
```

---

## 5. Videos.tsx — duplicate `export default function Videos()`

**Symptom**  
VS Code `get_errors` reported two `export default function Videos()` declarations in the same file (lines 20 and 357). TypeScript compilation would fail.

**Root Cause**  
A large `replace_string_in_file` operation rewrote the function starting from an `interface` definition, but the replacement range didn't include the closing `}` of the old function. This left the entire old function body intact below the new one.

**Fix**  
Search for the duplicate function body starting at the second `export default function Videos()` and delete it entirely, keeping only the first (new) version.

**Prevention**  
After any large file rewrite, run:
```powershell
cd client; npx tsc --noEmit
```
Zero output = zero errors.

---

## 6. Layout broken — content overflowing viewport

**Symptom**  
On mobile, the page scrolled past the screen edge. The chat button appeared off-screen or behind the browser toolbar.

**Root Cause**  
Vite's default `index.css` included:
```css
body { place-items: center; min-height: 100vh; }
h1   { font-size: 3.2em; }
```
These were centering the app container and overriding the compact header sizing.

The chat Submit button used `position: fixed` which broke layout on mobile browsers.

**Fix**  
Rewrote `index.css` to remove Vite defaults:
```css
html, body { height: 100%; overflow: hidden; }
*, *::before, *::after { box-sizing: border-box; }
```
Moved the chat button into a `.chat-controls` flex footer div instead of `position: fixed`.

---

## 7. Local Development — Setup & Common Issues

### Prerequisites

1. **Azure CLI** — logged in with `az login`
2. **Python 3.11+** with packages: `pip install -r server/requirements.txt`
3. **Node.js** — for the Vite frontend dev server
4. **RBAC role** — your `az login` user needs **Storage Blob Data Contributor** on the storage account (see issue 7b below)

### Starting locally

Run from the project root:
```powershell
.\start_local.ps1
```
This opens two terminal windows (backend on `:8000`, frontend on `:5173`). The backend takes ~30 seconds to start while it fetches an Azure credential token.

Alternatively, start each manually in separate terminals:
```powershell
# Terminal 1 — Backend
cd server
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd client
npx vite --host
```

Then open **http://localhost:5173** in your browser.

### How credential selection works

The backend (`server/main.py`) auto-detects the environment:
- **Azure** (Container Apps): Uses `ManagedIdentityCredential` — detected via `CONTAINER_APP_NAME` or `WEBSITE_SITE_NAME` env vars
- **Local**: Uses `AzureCliCredential` — requires a valid `az login` session

---

### 7a. Backend not starting — `ImportError: cannot import name 'genai'`

**Symptom**  
Running `python -m uvicorn main:app` fails with:
```
ImportError: cannot import name 'genai' from 'google'
```

**Root Cause**  
The `google-genai` package is not installed locally.

**Fix**  
```powershell
cd server
pip install -r requirements.txt
```

---

### 7b. "Failed to fetch" / `AuthorizationPermissionMismatch` on local

**Symptom**  
Clicking "My Videos" shows `Failed to fetch`. The backend returns `500 Internal Server Error` with:
```
ErrorCode:AuthorizationPermissionMismatch
This request is not authorized to perform this operation using this permission.
```

**Root Cause**  
In Azure, the backend's **Managed Identity** has the `Storage Blob Data Contributor` role. Locally, `AzureCliCredential` uses your personal `az login` account, which does **not** have that role by default.

**Fix**  
Assign the role to your user:
```powershell
# Get your user's Object ID
$userId = az ad signed-in-user show --query id -o tsv

# Get the storage account resource ID
$storageId = az storage account show --name stmemjz2jh --resource-group rg-memory-assistant --query id -o tsv

# Assign Storage Blob Data Contributor
az role assignment create --assignee $userId --role "Storage Blob Data Contributor" --scope $storageId
```

> **Note**: RBAC propagation can take up to 5 minutes. Restart the backend after the role is assigned.

---

### 7c. `DefaultAzureCredential` fails locally

**Symptom**  
Backend startup shows:
```
DefaultAzureCredential failed to retrieve a token from the included credentials.
ManagedIdentityCredential: [Errno 13] Permission denied
```

**Root Cause**  
`DefaultAzureCredential` tries multiple credential sources in order. On some Windows machines, the `ManagedIdentityCredential` step fails with a permission error on the Azure Arc agent token file, and other credential sources may also fail.

**Fix**  
The backend now uses `AzureCliCredential` directly for local development (instead of `DefaultAzureCredential`), which avoids this issue. Ensure you have a valid `az login` session:
```powershell
az login
az account show  # Verify you're logged in
```

---

### 7d. `.env` file not loaded — `GOOGLE_API_KEY` or `AZURE_STORAGE_ACCOUNT_URL` is None

**Symptom**  
Backend starts but Gemini calls fail or blob storage is not configured. Logs show:
```
GOOGLE_API_KEY not configured on server
```

**Root Cause**  
The `server/.env` file is missing or has placeholder values.

**Fix**  
Ensure `server/.env` contains real values:
```env
GOOGLE_API_KEY=<your-gemini-api-key>
AZURE_STORAGE_ACCOUNT_URL=https://<your-storage-account>.blob.core.windows.net
```

You can retrieve these from the deployed Azure app:
```powershell
az containerapp show --name app-memory-backend --resource-group rg-memory-assistant `
  --query "properties.template.containers[0].env[?name=='GOOGLE_API_KEY'].value" -o tsv

az containerapp show --name app-memory-backend --resource-group rg-memory-assistant `
  --query "properties.template.containers[0].env[?name=='AZURE_STORAGE_ACCOUNT_URL'].value" -o tsv
```

---

### 7e. Backend takes 30+ seconds to start

**Symptom**  
After running `start_local.ps1`, opening `http://localhost:5173` and clicking "My Videos" or "Ask Question" shows `Failed to fetch` for the first ~30 seconds.

**Root Cause**  
`AzureCliCredential` fetches an OAuth token from Azure AD at startup, which can take 20–30 seconds on the first call.

**Fix**  
This is expected. Wait for the backend terminal window to show:
```
Azure Blob Storage ready: https://...
INFO:     Uvicorn running on http://0.0.0.0:8000
```
before using the app.

---

## General Diagnostics

### Check backend live logs
```powershell
az containerapp logs show --name <your-backend-app> --resource-group <your-resource-group> --tail 50
```

### Check last deploy timestamp
```powershell
az containerapp show --name <your-backend-app> --resource-group <your-resource-group> --query "systemData.lastModifiedAt" -o tsv
az containerapp show --name <your-frontend-app> --resource-group <your-resource-group> --query "systemData.lastModifiedAt" -o tsv
```

### Test backend endpoints directly
```powershell
# Health check (Azure)
curl https://<your-backend-url>.azurecontainerapps.io/

# Health check (local)
curl http://localhost:8000/

# List videos (Azure)
curl https://<your-backend-url>.azurecontainerapps.io/videos

# List videos (local)
curl http://localhost:8000/videos
```

### Check local servers are running
```powershell
# Check if ports are listening
Get-NetTCPConnection -LocalPort 8000 -State Listen   # Backend
Get-NetTCPConnection -LocalPort 5173 -State Listen   # Frontend
```

### Force browser to reload after deploy
After a frontend deploy, the PWA service worker may serve a cached version.  
Press **Ctrl+Shift+R** (hard reload) or clear site data in DevTools → Application → Storage → Clear site data.
