from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import List, Any
import os
import re
import json
import mimetypes
import tempfile
import shutil
import traceback
import uuid
from google import genai
from google.genai import types
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.identity import ManagedIdentityCredential

# Configure Gemini
api_key = os.environ.get("GOOGLE_API_KEY")
client = None
if api_key:
    client = genai.Client(api_key=api_key)

# Configure Azure Blob Storage using Managed Identity (no connection string needed)
blob_service_client = None
container_name = "user-videos"
storage_account_url = os.environ.get("AZURE_STORAGE_ACCOUNT_URL")

if storage_account_url:
    try:
        credential = ManagedIdentityCredential()
        blob_service_client = BlobServiceClient(account_url=storage_account_url, credential=credential)
        # Ensure container exists
        container_client = blob_service_client.get_container_client(container_name)
        if not container_client.exists():
            container_client.create_container()
            print(f"Created Azure Blob container: {container_name}")
        else:
            print(f"Azure Blob Storage ready: {storage_account_url}")
    except Exception as e:
        print(f"Failed to initialize Azure Blob Storage: {e}")

app = FastAPI()

# Allow CORS for development/production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Memory Assistant API is running"}

@app.post("/chat-audio")
async def chat_with_audio(file: UploadFile = File(...)):
    if not client:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not configured on server")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            file_content = f.read()
        os.remove(tmp_path)

        mime_type = file.content_type.split(';')[0]
        print(f"Audio received. Size: {len(file_content)}, Mime: {mime_type}")

        # Build inventory context from all index blobs
        inventory_context = ""
        vid_map: dict[int, dict] = {}  # id -> {video_name, timestamp_start}
        if blob_service_client:
            try:
                container_client = blob_service_client.get_container_client(container_name)
                all_entries = []
                vid_id = 0
                for blob in container_client.list_blobs():
                    if blob.name.endswith('.index.json'):
                        try:
                            bc = blob_service_client.get_blob_client(container=container_name, blob=blob.name)
                            data = json.loads(bc.download_blob().readall())
                            video_name = blob.name[:-len('.index.json')]
                            match = re.match(r'^[0-9a-f-]{36}_(.+)$', video_name, re.I)
                            display = match.group(1) if match else video_name
                            for entry in data:
                                notes = f": {entry.get('notes')}" if entry.get('notes') else ""
                                ts = entry.get('timestamp_start')
                                ts_label = f" @{ts}s" if ts is not None else ""
                                all_entries.append(
                                    f"[VID:{vid_id}] {entry.get('object','?')} "
                                    f"→ {entry.get('location','?')} ({entry.get('room','?')})"
                                    f" [from: {display}]{notes}{ts_label}"
                                )
                                vid_map[vid_id] = {
                                    "video_name": video_name,
                                    "timestamp_start": ts,
                                }
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

        model_name = "gemini-flash-lite-latest"
        print(f"Sending audio to model: {model_name}")

        if inventory_context:
            prompt = (
                f"{inventory_context}"
                "You are a home inventory assistant. The user will ask a question via audio.\n"
                "RULE 1 — If the question asks where a specific item or object is located:\n"
                "  - Search the INVENTORY INDEX above.\n"
                "  - If found: state its exact location and room in the \"answer\" field. Do NOT include VID numbers, timestamps, or any index metadata in the answer text.\n"
                "  - If NOT found: reply exactly \"Sorry, I could not find [item] in the videos.\"\n"
                "RULE 2 — If the question is NOT about finding an item in the home:\n"
                "  - Reply exactly \"Sorry, I don't know the answer to that.\"\n"
                "If an item was found, return: {\"transcription\": \"...\", \"answer\": \"...\", \"video_id\": <VID number as integer>}\n"
                "The \"video_id\" must be the [VID:N] number from the matching index entry. It goes ONLY in the video_id field, NEVER in the answer text.\n"
                "If not found or not an item question, return: {\"transcription\": \"...\", \"answer\": \"...\"}\n"
                "Return ONLY a JSON object. No markdown, no extra text."
            )
        else:
            prompt = (
                "You are a home inventory assistant. No inventory has been loaded yet.\n"
                "Listen to the audio question.\n"
                "If the question is about finding an item: reply \"Sorry, I could not find [item] in the videos.\"\n"
                "Otherwise: reply \"Sorry, I don't know the answer to that.\"\n"
                "Return ONLY a JSON object: {\"transcription\": \"...\", \"answer\": \"...\"}\n"
                "No markdown, no extra text."
            )

        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=file_content, mime_type=mime_type)
                    ]
                )
            ]
        )

        try:
            text_resp = response.text.replace('```json', '').replace('```', '').strip()
            parsed = json.loads(text_resp)
            # Resolve video_id to blob name and timestamp
            vid_id = parsed.pop('video_id', None)
            if vid_id is not None and isinstance(vid_id, int) and vid_id in vid_map:
                matched = vid_map[vid_id]
                parsed['video_name'] = matched["video_name"]
                parsed['timestamp_start'] = matched["timestamp_start"]
                print(f"Matched video: {matched['video_name']} @{matched['timestamp_start']}s")
            else:
                parsed['video_name'] = None
                parsed['timestamp_start'] = None
            return parsed
        except:
            return {"transcription": "(Could not parse transcription)", "answer": response.text, "video_name": None, "timestamp_start": None}

    except Exception as e:
        traceback.print_exc()
        print(f"### GEMINI ERROR ###: {e}")
        return {
            "error": str(e),
            "response": "I'm sorry, I'm having trouble connecting to the AI service right now. Please try again later.",
            "transcription": "(Error connecting to AI)"
        }

@app.post("/analyze-video")
async def analyze_video(file: UploadFile = File(...)):
    filename = file.filename
    blob_url = None
    unique_filename = None

    if not blob_service_client:
        print("Blob storage not configured. File not persisted.")
        return {"filename": filename, "error": "Storage not configured."}

    # Step 1: Save video to temp file
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        # Step 2: Upload video blob
        unique_filename = f"{uuid.uuid4()}_{filename}"
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=unique_filename)
        content_type = file.content_type or mimetypes.guess_type(filename)[0] or "video/mp4"

        with open(tmp_path, "rb") as data:
            blob_client.upload_blob(data, content_settings=ContentSettings(content_type=content_type))

        blob_url = blob_client.url
        print(f"Uploaded video blob: {blob_url}")

        # Step 3: Analyze with Gemini to extract inventory index
        inventory_items = []
        if client:
            try:
                print(f"Analyzing video with Gemini: {unique_filename}")
                with open(tmp_path, "rb") as f:
                    video_bytes = f.read()

                analysis_prompt = (
                    "Watch this home video carefully. Your job is to create an inventory index. "
                    "For every physical object you can clearly see, record: "
                    "object (item name), location (specific spot e.g. 'top shelf', 'left drawer'), "
                    "room (which room), notes (color/brand/identifying detail if visible), "
                    "timestamp_start (the approximate time in seconds when the object first appears in the video). "
                    "Return ONLY a JSON array, no markdown:\n"
                    '[{"object":"...","location":"...","room":"...","notes":"...","timestamp_start":0}]'
                )

                response = client.models.generate_content(
                    model="gemini-flash-lite-latest",
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(text=analysis_prompt),
                                types.Part.from_bytes(data=video_bytes, mime_type=content_type)
                            ]
                        )
                    ]
                )

                text_resp = response.text.replace('```json', '').replace('```', '').strip()
                inventory_items = json.loads(text_resp)
                if not isinstance(inventory_items, list):
                    inventory_items = []
                print(f"Extracted {len(inventory_items)} inventory items")

                # Step 4: Save index as companion blob
                index_blob_name = f"{unique_filename}.index.json"
                index_bc = blob_service_client.get_blob_client(container=container_name, blob=index_blob_name)
                index_bc.upload_blob(
                    json.dumps(inventory_items, ensure_ascii=False),
                    content_settings=ContentSettings(content_type="application/json"),
                    overwrite=True
                )
                print(f"Saved index blob: {index_blob_name}")

            except Exception as ae:
                print(f"Gemini analysis failed: {ae}")
                traceback.print_exc()
                inventory_items = []

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
        "items": inventory_items[:10]  # Return first 10 for display
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
