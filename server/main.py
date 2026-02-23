from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import List, Any
import os
import re
import json
import base64
import mimetypes
import tempfile
import shutil
import traceback
import uuid
import time
import requests as _http
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.storage.blob import BlobServiceClient, ContentSettings

# Load .env file when running locally (no-op in production where real env vars are set)
load_dotenv()

# ── Shared Azure credential (used for OpenAI, Storage, and Content Understanding)
_az_credential = DefaultAzureCredential()

# ── Azure OpenAI / GPT-5.2 (keyless — Managed Identity in prod, az login locally)
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.2")
_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
if not _endpoint:
    raise RuntimeError("AZURE_OPENAI_ENDPOINT environment variable is not set")

_token_provider = get_bearer_token_provider(
    _az_credential,
    "https://cognitiveservices.azure.com/.default"
)
client = AzureOpenAI(
    azure_endpoint=_endpoint,
    azure_ad_token_provider=_token_provider,
    api_version="2025-04-01-preview",
)
print(f"Azure OpenAI client initialized (keyless): {_endpoint}, deployment={AZURE_OPENAI_DEPLOYMENT}")

# ── Azure AI Content Understanding (same resource endpoint as OpenAI) ─────
AZURE_CU_API_VERSION = "2024-12-01-preview"

def _cu_headers() -> dict:
    """Bearer token headers for Content Understanding REST API."""
    token = _az_credential.get_token("https://cognitiveservices.azure.com/.default").token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def transcribe_audio(audio_path: str, mime_type: str) -> str:
    """Transcribe audio using Azure AI Content Understanding (prebuilt-audioAnalyzer)."""
    with open(audio_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    base_url = _endpoint.rstrip("/")
    analyze_url = (
        f"{base_url}/contentunderstanding/analyzers/"
        f"prebuilt-audioAnalyzer:analyze?api-version={AZURE_CU_API_VERSION}"
    )
    body = {"content": content_b64, "mimeType": mime_type or "audio/webm"}

    resp = _http.post(analyze_url, headers=_cu_headers(), json=body, timeout=60)
    resp.raise_for_status()

    operation_url = resp.headers.get("Operation-Location")
    if not operation_url:
        raise RuntimeError(f"Content Understanding: no Operation-Location. Response: {resp.text[:500]}")

    # Poll until complete (max ~3 minutes)
    for _ in range(60):
        time.sleep(3)
        r = _http.get(operation_url, headers=_cu_headers(), timeout=30)
        r.raise_for_status()
        data = r.json()
        status = data.get("status", "running")
        if status == "succeeded":
            try:
                return data["result"]["contents"][0]["fields"]["transcript"]["valueString"]
            except (KeyError, IndexError):
                return str(data.get("result", ""))
        if status in ("failed", "canceled"):
            raise RuntimeError(f"Content Understanding failed: {data}")

    raise RuntimeError("Content Understanding audio analysis timed out after 3 minutes")

# ── Azure Blob Storage (Managed Identity — no connection string) ───────────
blob_service_client = None
container_name = "user-videos"
storage_account_url = os.environ.get("AZURE_STORAGE_ACCOUNT_URL")

if storage_account_url:
    try:
        blob_service_client = BlobServiceClient(account_url=storage_account_url, credential=_az_credential)
        container_client = blob_service_client.get_container_client(container_name)
        if not container_client.exists():
            container_client.create_container()
            print(f"Created Azure Blob container: {container_name}")
        else:
            print(f"Azure Blob Storage ready: {storage_account_url}")
    except Exception as e:
        print(f"Failed to initialize Azure Blob Storage: {e}")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shared helpers ─────────────────────────────────────────────────────────

def build_inventory_context() -> tuple[str, dict]:
    """Load all .index.json blobs and return a context string + vid_id→blob_name map."""
    inventory_context = ""
    vid_map: dict[int, str] = {}
    if not blob_service_client:
        return inventory_context, vid_map
    try:
        cc = blob_service_client.get_container_client(container_name)
        all_entries = []
        vid_id = 0
        for blob in cc.list_blobs():
            if blob.name.endswith('.index.json'):
                try:
                    bc = blob_service_client.get_blob_client(container=container_name, blob=blob.name)
                    data = json.loads(bc.download_blob().readall())
                    video_name = blob.name[:-len('.index.json')]
                    match = re.match(r'^[0-9a-f-]{36}_(.+)$', video_name, re.I)
                    display = match.group(1) if match else video_name
                    for entry in data:
                        notes = f": {entry.get('notes')}" if entry.get('notes') else ""
                        all_entries.append(
                            f"[VID:{vid_id}] {entry.get('object','?')} "
                            f"→ {entry.get('location','?')} ({entry.get('room','?')})"
                            f" [from: {display}]{notes}"
                        )
                        vid_map[vid_id] = video_name
                        vid_id += 1
                except Exception as ie:
                    print(f"Failed to read index {blob.name}: {ie}")
        if all_entries:
            inventory_context = (
                "INVENTORY INDEX (from uploaded videos):\n"
                + "\n".join(all_entries)
                + "\n\n"
            )
            print(f"Loaded {len(all_entries)} inventory entries for context")
    except Exception as ce:
        print(f"Failed to load inventory context: {ce}")
    return inventory_context, vid_map


def build_chat_prompt(inventory_context: str) -> str:
    """Return the system prompt for the chat-audio endpoint."""
    if inventory_context:
        return (
            f"{inventory_context}"
            "You are a home inventory assistant. The user's question has already been transcribed.\n"
            "RULE 1 — If the question asks where a specific item or object is located:\n"
            "  - Search the INVENTORY INDEX above.\n"
            "  - If found: state its exact location and room. Set video_id to the matching VID number (integer).\n"
            "  - If NOT found: reply exactly \"Sorry, I could not find [item] in the videos.\" and set video_id to null.\n"
            "RULE 2 — If the question is NOT about finding an item in the home:\n"
            "  - Reply exactly \"Sorry, I don't know the answer to that.\" and set video_id to null.\n"
            "Return ONLY a JSON object: {\"answer\": \"...\", \"video_id\": <integer or null>}\n"
            "No markdown, no extra text."
        )
    return (
        "You are a home inventory assistant. No inventory has been loaded yet.\n"
        "The user's question has already been transcribed.\n"
        "If the question is about finding an item: reply \"Sorry, I could not find [item] in the videos.\"\n"
        "Otherwise: reply \"Sorry, I don't know the answer to that.\"\n"
        "Return ONLY a JSON object: {\"answer\": \"...\", \"video_id\": null}\n"
        "No markdown, no extra text."
    )


def parse_ai_response(text: str, vid_map: dict) -> dict:
    """Parse a JSON response from any AI provider and resolve video_id → blob name."""
    text = text.replace('```json', '').replace('```', '').strip()
    parsed = json.loads(text)
    vid_id = parsed.pop('video_id', None)
    if vid_id is not None and isinstance(vid_id, int) and vid_id in vid_map:
        parsed['video_name'] = vid_map[vid_id]
        print(f"Matched video: {vid_map[vid_id]}")
    else:
        parsed['video_name'] = None
    return parsed


def extract_video_frames(video_path: str, num_frames: int = 12) -> list[str]:
    """
    Extract evenly-spaced frames from a video file.
    Returns a list of base64-encoded JPEG strings for use as image_url content blocks.
    """
    import cv2
    frames = []
    cap = cv2.VideoCapture(video_path)
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            return frames
        for i in range(num_frames):
            idx = int(i * total / num_frames)
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                frames.append(base64.b64encode(buf).decode())
    finally:
        cap.release()
    return frames

@app.get("/")
def read_root():
    return {"message": "Memory Assistant API is running", "model": AZURE_OPENAI_DEPLOYMENT}

@app.post("/chat-audio")
async def chat_with_audio(file: UploadFile = File(...)):
    tmp_path = None
    try:
        suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        mime_type = file.content_type.split(';')[0]
        print(f"Audio received. Size: {os.path.getsize(tmp_path)}, Mime: {mime_type}")

        # Step 1: Transcribe audio with Azure AI Content Understanding
        transcription = transcribe_audio(tmp_path, mime_type)
        print(f"Transcription: {transcription}")

        # Step 2: Query GPT-5.2 with transcription text + inventory context
        inventory_context, vid_map = build_inventory_context()
        system_prompt = build_chat_prompt(inventory_context)

        response = client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcription},
            ],
        )
        text_resp = response.choices[0].message.content or ""
        try:
            result = parse_ai_response(text_resp, vid_map)
            result["transcription"] = transcription
            return result
        except Exception:
            return {"transcription": transcription, "answer": text_resp, "video_name": None}

    except Exception as e:
        traceback.print_exc()
        print(f"### AZURE OPENAI ERROR ###: {e}")
        return {
            "error": str(e),
            "response": "I'm sorry, I'm having trouble connecting to the AI service right now. Please try again later.",
            "transcription": "(Error connecting to AI)"
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/analyze-video")
async def analyze_video(file: UploadFile = File(...)):
    filename = file.filename
    blob_url = None
    unique_filename = None

    if not blob_service_client:
        print("Blob storage not configured. File not persisted.")
        return {"filename": filename, "error": "Storage not configured."}

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        # Upload video blob
        unique_filename = f"{uuid.uuid4()}_{filename}"
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=unique_filename)
        content_type = file.content_type or mimetypes.guess_type(filename)[0] or "video/mp4"

        with open(tmp_path, "rb") as data:
            blob_client.upload_blob(data, content_settings=ContentSettings(content_type=content_type))

        blob_url = blob_client.url
        print(f"Uploaded video blob: {blob_url}")

        inventory_items = []
        analysis_prompt = (
            "Watch this home video carefully. Your job is to create an inventory index. "
            "For every physical object you can clearly see, record: "
            "object (item name), location (specific spot e.g. 'top shelf', 'left drawer'), "
            "room (which room), notes (color/brand/identifying detail if visible). "
            "Return ONLY a JSON array, no markdown:\n"
            '[{"object":"...","location":"...","room":"...","notes":"..."}]'
        )

        try:
            print(f"Extracting video frames for Azure OpenAI analysis: {unique_filename}")
            frames_b64 = extract_video_frames(tmp_path, num_frames=12)
            if not frames_b64:
                raise ValueError("No frames could be extracted from video")
            content_parts: list = [{"type": "text", "text": analysis_prompt}]
            for frame_b64 in frames_b64:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{frame_b64}",
                        "detail": "auto",
                    },
                })
            response = client.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=[{"role": "user", "content": content_parts}],
            )
            text_resp = (response.choices[0].message.content or "[]").replace('```json', '').replace('```', '').strip()
            inventory_items = json.loads(text_resp)
            if not isinstance(inventory_items, list):
                inventory_items = []
            print(f"Extracted {len(inventory_items)} inventory items")
        except Exception as ae:
            print(f"Azure OpenAI video analysis failed: {ae}")
            traceback.print_exc()
            inventory_items = []

        # Save companion index blob regardless of provider
        if inventory_items:
            index_blob_name = f"{unique_filename}.index.json"
            index_bc = blob_service_client.get_blob_client(container=container_name, blob=index_blob_name)
            index_bc.upload_blob(
                json.dumps(inventory_items, ensure_ascii=False),
                content_settings=ContentSettings(content_type="application/json"),
                overwrite=True
            )
            print(f"Saved index blob: {index_blob_name}")

    except Exception as e:
        print(f"Azure Blob Upload Failed: {e}")
        traceback.print_exc()
        os.remove(tmp_path)
        return {"filename": filename, "error": "Storage failed, file not persisted."}
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {
        "filename": unique_filename,
        "url": blob_url,
        "item_count": len(inventory_items),
        "items": inventory_items[:10]
    }

@app.get("/videos")
def list_videos():
    if not blob_service_client:
        return []
    container_client = blob_service_client.get_container_client(container_name)
    all_blobs = list(container_client.list_blobs())
    index_names = {b.name for b in all_blobs if b.name.endswith('.index.json')}
    videos = []
    for blob in all_blobs:
        if blob.name.endswith('.index.json'):
            continue
        videos.append({
            "name": blob.name,
            "size": blob.size,
            "last_modified": blob.last_modified.isoformat() if blob.last_modified else None,
            "has_index": f"{blob.name}.index.json" in index_names
        })
    videos.sort(key=lambda x: x["last_modified"] or "", reverse=True)
    return videos

@app.get("/videos/{blob_name:path}/stream")
async def stream_video(blob_name: str, request: Request):
    if not blob_service_client:
        raise HTTPException(status_code=503, detail="Storage not configured")
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        props = blob_client.get_blob_properties()
        blob_size = props.size
        content_type = props.content_settings.content_type or mimetypes.guess_type(blob_name)[0] or "video/mp4"

        range_header = request.headers.get("range")
        if range_header:
            match = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if match:
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else blob_size - 1
                end = min(end, blob_size - 1)
                length = end - start + 1

                def generate_range():
                    stream = blob_client.download_blob(offset=start, length=length)
                    for chunk in stream.chunks():
                        yield chunk

                return StreamingResponse(
                    generate_range(),
                    status_code=206,
                    headers={
                        "Content-Range": f"bytes {start}-{end}/{blob_size}",
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(length),
                        "Content-Type": content_type,
                    }
                )

        def generate_full():
            stream = blob_client.download_blob()
            for chunk in stream.chunks():
                yield chunk

        return StreamingResponse(
            generate_full(),
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(blob_size),
                "Content-Type": content_type,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.delete("/videos/{blob_name:path}")
def delete_video(blob_name: str):
    if not blob_service_client:
        raise HTTPException(status_code=503, detail="Storage not configured")
    try:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        blob_client.delete_blob()
        # Cascade delete companion index if it exists
        try:
            index_bc = blob_service_client.get_blob_client(container=container_name, blob=f"{blob_name}.index.json")
            index_bc.delete_blob()
            print(f"Deleted companion index for: {blob_name}")
        except:
            pass
        return {"deleted": blob_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/videos/{blob_name:path}/index")
def get_video_index(blob_name: str):
    if not blob_service_client:
        raise HTTPException(status_code=503, detail="Storage not configured")
    try:
        index_bc = blob_service_client.get_blob_client(container=container_name, blob=f"{blob_name}.index.json")
        data = json.loads(index_bc.download_blob().readall())
        return data
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"No index found: {e}")


@app.put("/videos/{blob_name:path}/index")
def update_video_index(blob_name: str, entries: List[Any] = Body(...)):
    if not blob_service_client:
        raise HTTPException(status_code=503, detail="Storage not configured")
    try:
        index_bc = blob_service_client.get_blob_client(container=container_name, blob=f"{blob_name}.index.json")
        index_bc.upload_blob(
            json.dumps(entries, ensure_ascii=False),
            content_settings=ContentSettings(content_type="application/json"),
            overwrite=True
        )
        return {"updated": blob_name, "item_count": len(entries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
