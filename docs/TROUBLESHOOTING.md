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

## 2. Google Gemini 429 — Quota Exhausted *(v1 — Gemini era, now resolved)*

> **Note**: The backend has since migrated from Google Gemini to **Azure OpenAI (GPT-5.2)** with **Azure AI Content Understanding** for transcription. This section is kept as a historical record of the v1 architecture.

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

## 3. AI not answering general knowledge questions *(v1 — Gemini era, now resolved)*

> **Note**: This issue was specific to the Google Gemini multimodal pathway. The current v2 architecture (Azure AI Content Understanding for transcription + Azure OpenAI GPT-5.2 for chat) handles this differently — transcription and Q&A are separate steps by design, with explicit prompt rules controlling scope.

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
# Health check
curl https://<your-backend-url>.azurecontainerapps.io/

# List videos
curl https://<your-backend-url>.azurecontainerapps.io/videos
```

### Force browser to reload after deploy
After a frontend deploy, the PWA service worker may serve a cached version.  
Press **Ctrl+Shift+R** (hard reload) or clear site data in DevTools → Application → Storage → Clear site data.
