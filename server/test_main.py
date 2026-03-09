"""
Unit tests for FindIt backend API endpoints.
Uses mocks for Azure Blob Storage and Google Gemini to test without external dependencies.
Run: cd server && python -m pytest test_main.py -v
"""

import json
import io
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient, ASGITransport


# ── Helpers ──────────────────────────────────────────────────────────

def _make_blob(name: str, size: int = 1024, has_last_modified: bool = True):
    """Create a mock blob object matching Azure SDK shape."""
    blob = MagicMock()
    blob.name = name
    blob.size = size
    blob.last_modified = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc) if has_last_modified else None
    return blob


def _make_index_json(items: list[dict]) -> bytes:
    return json.dumps(items).encode("utf-8")


SAMPLE_INDEX = [
    {"object": "reading glasses", "location": "bedside table", "room": "bedroom", "notes": "red frame", "timestamp_start": 5},
    {"object": "car keys", "location": "hook by the front door", "room": "hallway", "notes": "", "timestamp_start": 18},
]


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_blob_service():
    """Patch blob_service_client in main module so endpoints use mocked storage."""
    with patch("main.blob_service_client") as mock_bsc:
        yield mock_bsc


@pytest.fixture
def mock_gemini():
    """Patch the Gemini client in main module."""
    with patch("main.client") as mock_client:
        yield mock_client


@pytest.fixture
def app():
    from main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def transport(app):
    return ASGITransport(app=app)


# ── 1. GET /videos — List Videos ────────────────────────────────────

class TestListVideos:

    @pytest.mark.anyio
    async def test_returns_videos_with_index_flag(self, transport, mock_blob_service):
        """Videos list should include has_index=True when companion .index.json exists."""
        video_blob = _make_blob("abc123_myvideo.mp4", size=5_000_000)
        index_blob = _make_blob("abc123_myvideo.mp4.index.json", size=512)

        container_client = MagicMock()
        container_client.list_blobs.return_value = [video_blob, index_blob]
        mock_blob_service.get_container_client.return_value = container_client

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/videos")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "abc123_myvideo.mp4"
        assert data[0]["has_index"] is True
        assert data[0]["size"] == 5_000_000

    @pytest.mark.anyio
    async def test_returns_video_without_index(self, transport, mock_blob_service):
        """Videos without a companion .index.json should have has_index=False."""
        video_blob = _make_blob("def456_clip.mp4", size=2_000_000)

        container_client = MagicMock()
        container_client.list_blobs.return_value = [video_blob]
        mock_blob_service.get_container_client.return_value = container_client

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/videos")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["has_index"] is False

    @pytest.mark.anyio
    async def test_returns_empty_when_no_storage(self, transport):
        """When blob storage is not configured, /videos returns empty list."""
        with patch("main.blob_service_client", None):
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/videos")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.anyio
    async def test_videos_sorted_by_last_modified_desc(self, transport, mock_blob_service):
        """Videos should be sorted newest first."""
        old_blob = _make_blob("old_video.mp4")
        old_blob.last_modified = datetime(2025, 1, 1, tzinfo=timezone.utc)
        new_blob = _make_blob("new_video.mp4")
        new_blob.last_modified = datetime(2026, 6, 1, tzinfo=timezone.utc)

        container_client = MagicMock()
        container_client.list_blobs.return_value = [old_blob, new_blob]
        mock_blob_service.get_container_client.return_value = container_client

        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/videos")

        data = resp.json()
        assert data[0]["name"] == "new_video.mp4"
        assert data[1]["name"] == "old_video.mp4"


# ── 2. POST /analyze-video — Upload & Analyze ───────────────────────

class TestAnalyzeVideo:

    @pytest.mark.anyio
    async def test_upload_and_analyze_success(self, transport, mock_blob_service, mock_gemini):
        """Upload should store blob, call Gemini, save index, and return items."""
        # Mock blob upload
        blob_client = MagicMock()
        blob_client.url = "https://storage.blob.core.windows.net/user-videos/test.mp4"
        mock_blob_service.get_blob_client.return_value = blob_client

        # Mock Gemini response
        gemini_response = MagicMock()
        gemini_response.text = json.dumps(SAMPLE_INDEX)
        mock_gemini.models.generate_content.return_value = gemini_response

        video_content = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/analyze-video",
                files={"file": ("test.mp4", io.BytesIO(video_content), "video/mp4")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["item_count"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["object"] == "reading glasses"

        # Verify blob upload was called twice (video + index JSON)
        assert blob_client.upload_blob.call_count == 2
        # Verify Gemini was called
        mock_gemini.models.generate_content.assert_called_once()

    @pytest.mark.anyio
    async def test_upload_no_storage_returns_error(self, transport, mock_gemini):
        """When storage is not configured, upload should return error."""
        with patch("main.blob_service_client", None):
            video_content = b"\x00" * 50
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/analyze-video",
                    files={"file": ("test.mp4", io.BytesIO(video_content), "video/mp4")},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["error"] == "Storage not configured."

    @pytest.mark.anyio
    async def test_upload_gemini_failure_still_saves_video(self, transport, mock_blob_service, mock_gemini):
        """If Gemini analysis fails, the video should still be saved with 0 items."""
        blob_client = MagicMock()
        blob_client.url = "https://storage.blob.core.windows.net/user-videos/test.mp4"
        mock_blob_service.get_blob_client.return_value = blob_client

        # Gemini raises an exception
        mock_gemini.models.generate_content.side_effect = Exception("Gemini quota exceeded")

        video_content = b"\x00" * 50
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/analyze-video",
                files={"file": ("test.mp4", io.BytesIO(video_content), "video/mp4")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["item_count"] == 0
        # Video blob was still uploaded
        blob_client.upload_blob.assert_called_once()


# ── 3. POST /chat-audio — Ask Question ──────────────────────────────

class TestChatAudio:

    @pytest.mark.anyio
    async def test_chat_with_inventory_match(self, transport, mock_blob_service, mock_gemini):
        """Voice query should return answer with matched video when item is found."""
        # Mock inventory index blobs
        video_blob = _make_blob("uuid1_walkthrough.mp4")
        index_blob = _make_blob("uuid1_walkthrough.mp4.index.json")

        container_client = MagicMock()
        container_client.list_blobs.return_value = [video_blob, index_blob]
        mock_blob_service.get_container_client.return_value = container_client

        # Mock index download
        index_bc = MagicMock()
        index_bc.download_blob.return_value.readall.return_value = _make_index_json(SAMPLE_INDEX)
        mock_blob_service.get_blob_client.return_value = index_bc

        # Mock Gemini response with video_id match
        gemini_response = MagicMock()
        gemini_response.text = json.dumps({
            "transcription": "Where are my glasses?",
            "answer": "Your reading glasses are on the bedside table in the bedroom.",
            "video_id": 0
        })
        mock_gemini.models.generate_content.return_value = gemini_response

        audio_content = b"\x00" * 100
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/chat-audio",
                files={"file": ("query.webm", io.BytesIO(audio_content), "audio/webm")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["transcription"] == "Where are my glasses?"
        assert "bedside table" in data["answer"]
        assert data["video_name"] == "uuid1_walkthrough.mp4"
        assert data["timestamp_start"] == 5

    @pytest.mark.anyio
    async def test_chat_item_not_found(self, transport, mock_blob_service, mock_gemini):
        """When the item is not in inventory, response should have no video match."""
        container_client = MagicMock()
        container_client.list_blobs.return_value = []
        mock_blob_service.get_container_client.return_value = container_client

        gemini_response = MagicMock()
        gemini_response.text = json.dumps({
            "transcription": "Where is my passport?",
            "answer": "I'm sorry, I couldn't find your passport in the videos we have."
        })
        mock_gemini.models.generate_content.return_value = gemini_response

        audio_content = b"\x00" * 100
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/chat-audio",
                files={"file": ("query.webm", io.BytesIO(audio_content), "audio/webm")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["video_name"] is None
        assert data["timestamp_start"] is None

    @pytest.mark.anyio
    async def test_chat_no_gemini_key(self, transport, mock_blob_service):
        """Without GOOGLE_API_KEY configured, /chat-audio should return 500."""
        with patch("main.client", None):
            audio_content = b"\x00" * 100
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/chat-audio",
                    files={"file": ("query.webm", io.BytesIO(audio_content), "audio/webm")},
                )

        assert resp.status_code == 500

    @pytest.mark.anyio
    async def test_chat_gemini_error_returns_friendly_message(self, transport, mock_blob_service, mock_gemini):
        """If Gemini raises an error, the response should contain a user-friendly message."""
        container_client = MagicMock()
        container_client.list_blobs.return_value = []
        mock_blob_service.get_container_client.return_value = container_client

        mock_gemini.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")

        audio_content = b"\x00" * 100
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/chat-audio",
                files={"file": ("query.webm", io.BytesIO(audio_content), "audio/webm")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert "try again" in data["response"].lower()


# ── 4. Health Check ──────────────────────────────────────────────────

class TestHealthCheck:

    @pytest.mark.anyio
    async def test_root_endpoint(self, transport):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/")

        assert resp.status_code == 200
        assert resp.json()["message"] == "FindIt API is running"
