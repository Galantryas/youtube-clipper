import os
import sys
import uuid
import json
import time
import asyncio
import warnings

# Suppress upstream library deprecation notices
warnings.filterwarnings("ignore", message=".*Deprecated Feature.*")
warnings.filterwarnings("ignore", message=".*deprecated.*")
os.environ["PYTHONWARNINGS"] = "ignore"

from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .utils import (
    BASE_DIR, OUTPUT_DIR, TEMP_DIR,
    sanitize_filename, get_output_dir, open_folder, format_time, get_ffmpeg_path
)
from .downloader import get_video_info, download_source_video, extract_video_id
from .subtitle_engine import fetch_youtube_transcript, detect_smart_clips
from .clip_engine import process_single_clip
from .autopilot.scheduler import autopilot_engine
from .autopilot.config_manager import load_autopilot_config, save_autopilot_config
from .autopilot.history_manager import load_autopilot_history, clear_autopilot_history
from .autopilot.trending_fetcher import COUNTRY_MAP, COUNTRY_EMOJIS

app = FastAPI(title="YouTube Clipper Pro API", version="1.0.0")

@app.on_event("startup")
async def on_startup():
    autopilot_engine.start()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Thread pool for CPU/FFmpeg tasks
executor = ThreadPoolExecutor(max_workers=3)

# In-memory jobs tracking
jobs: Dict[str, Dict[str, Any]] = {}


class InfoRequest(BaseModel):
    url: str


class CustomClipItem(BaseModel):
    start_time: float
    duration: float
    title: Optional[str] = "Clip"


class ClipRequest(BaseModel):
    url: str
    aspect_ratio: str = "9:16"  # "9:16", "1:1", "16:9", "4:5"
    resolution: str = "1080p"   # "1080p", "720p", "4k"
    clip_count: int = 3
    target_duration: float = 30.0
    face_follow: Union[str, bool] = "single"  # "single", "dynamic", "split", "none"
    subtitle_option: str = "tiktok"  # "none", "tiktok", "clean", "srt_only"
    custom_clips: Optional[List[CustomClipItem]] = None


class OpenFolderRequest(BaseModel):
    folder_path: Optional[str] = None
    video_id: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Frontend loading...</h1>", status_code=200)
    return FileResponse(index_file)


@app.post("/api/info")
async def fetch_info(req: InfoRequest):
    """Fetches YouTube video metadata and suggested clips."""
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(executor, get_video_info, req.url)
        
        # Try fetching transcript for smart moments
        video_id = info["id"]
        transcript = await loop.run_in_executor(executor, fetch_youtube_transcript, video_id)
        
        suggested_clips = detect_smart_clips(
            transcript=transcript,
            total_duration=info["duration"],
            clip_count=3,
            target_duration=30.0,
            video_title=info.get("title", "")
        )

        info["suggested_clips"] = suggested_clips
        info["has_captions"] = len(transcript) > 0

        # Check if already cached locally in any folder
        is_cached = False
        for past_folder in OUTPUT_DIR.glob(f"*_{video_id}"):
            cand = past_folder / "source_video.mp4"
            if cand.exists() and cand.stat().st_size > 50000:
                is_cached = True
                break
        info["is_cached"] = is_cached

        return {"success": True, "data": info, "info": info}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def run_clip_job(job_id: str, req_data: Dict[str, Any]):
    """Background worker that orchestrates downloading, tracking, slicing, subtitles, and saving."""
    job = jobs[job_id]
    url = req_data["url"]
    aspect_ratio = req_data.get("aspect_ratio", "9:16")
    resolution = req_data.get("resolution", "1080p")
    clip_count = req_data.get("clip_count", 3)
    target_duration = float(req_data.get("target_duration", 30.0))
    face_follow = req_data.get("face_follow", True)
    subtitle_option = req_data.get("subtitle_option", "tiktok")
    custom_clips = req_data.get("custom_clips")

    try:
        # Step 1: Info & Preparation
        job["stage"] = "info"
        job["progress"] = 6
        job["message"] = "Fetching video details and metadata..."
        
        info = get_video_info(url)
        video_id = info["id"]
        video_title = info["title"]
        total_duration = info["duration"]

        # Step 2: Dedicated Video Folder
        video_folder = get_output_dir(video_title, video_id)
        source_download_path = video_folder / "source_video.mp4"

        # Step 3: Fetch Transcripts & NLP boundary scoring
        job["progress"] = 12
        job["message"] = "Extracting video transcript for subtitles & NLP hooks..."
        transcript = fetch_youtube_transcript(video_id)

        # Step 4: Determine clip timestamps
        if custom_clips and len(custom_clips) > 0:
            clips_to_process = [
                {
                    "clip_index": i + 1,
                    "title": c.get("title") or f"Clip {i+1}",
                    "start_time": float(c["start_time"]),
                    "duration": float(c["duration"]),
                    "end_time": float(c["start_time"]) + float(c["duration"])
                }
                for i, c in enumerate(custom_clips)
            ]
        else:
            job["progress"] = 16
            job["message"] = "Analyzing sentence boundaries and viral hook moments..."
            clips_to_process = detect_smart_clips(
                transcript=transcript,
                total_duration=total_duration,
                clip_count=clip_count,
                target_duration=target_duration,
                video_title=video_title
            )

        job["total_clips"] = len(clips_to_process)
        job["clips_done"] = 0
        job["progress"] = 18
        job["message"] = f"Calculated {len(clips_to_process)} optimal clip moments."

        # Check if source video already exists in target folder or any previous folder with this video_id
        existing_source = None
        if source_download_path.exists() and source_download_path.stat().st_size > 50000:
            existing_source = source_download_path
        else:
            for past_folder in OUTPUT_DIR.glob(f"*_{video_id}"):
                cand = past_folder / "source_video.mp4"
                if cand.exists() and cand.stat().st_size > 50000:
                    import shutil
                    shutil.copy2(cand, source_download_path)
                    existing_source = source_download_path
                    break

        info["is_cached"] = existing_source is not None

        # Step 5: Download Source Video (or reuse existing)
        job["stage"] = "download"
        if existing_source:
            job["progress"] = 50
            job["message"] = "⚡ Existing video found in local library! Skipping re-download..."
            time.sleep(0.5)
        else:
            job["progress"] = 20
            job["message"] = "Downloading source video from YouTube..."

            def download_progress(p_info):
                pct = p_info.get("percent", 0)
                job["progress"] = round(20 + (pct * 0.3), 1)
                job["message"] = p_info.get("message", "Downloading video...")

            download_source_video(
                url=url,
                output_filepath=source_download_path,
                target_res=resolution,
                progress_callback=download_progress
            )

        # Step 6: Process each clip (preserving existing clips from previous runs)
        job["stage"] = "face"
        job["progress"] = 52
        generated_clips = []

        # Load existing clips from previous runs if metadata exists
        meta_json_path = video_folder / "metadata.json"
        existing_clips = []
        if meta_json_path.exists():
            try:
                with open(meta_json_path, "r", encoding="utf-8") as f:
                    prev_meta = json.load(f)
                    existing_clips = prev_meta.get("clips", [])
            except Exception:
                pass

        # Existing clip files on disk
        existing_mp4_files = list(video_folder.glob("clip_*.mp4"))
        base_clip_index = len(existing_mp4_files)

        total_num_clips = len(clips_to_process)
        for idx, clip_def in enumerate(clips_to_process):
            clip_idx = base_clip_index + idx + 1
            # Unique filename with aspect ratio tag to prevent collision
            safe_title = sanitize_filename(clip_def['title'])
            clip_name = f"clip_{clip_idx:02d}_{aspect_ratio.replace(':', 'x')}_{safe_title}.mp4"
            out_clip_path = video_folder / clip_name

            clip_progress_base = 52 + (idx / total_num_clips) * 42
            clip_progress_span = 42 / total_num_clips

            def single_clip_progress(c_info):
                c_pct = c_info.get("percent", 0)
                if c_pct < 40:
                    job["stage"] = "face"
                else:
                    job["stage"] = "render"
                job["progress"] = round(clip_progress_base + (c_pct / 100.0) * clip_progress_span, 1)
                job["message"] = f"Clip {idx + 1}/{total_num_clips}: {c_info.get('message', 'Processing...')}"

            process_single_clip(
                source_video_path=source_download_path,
                output_clip_path=out_clip_path,
                start_time=clip_def["start_time"],
                duration=clip_def["duration"],
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                face_follow=face_follow,
                subtitle_option=subtitle_option,
                transcript=transcript,
                progress_callback=single_clip_progress
            )

            # Check if SRT was created
            srt_path = out_clip_path.with_suffix(".srt")
            has_srt = srt_path.exists()

            clip_rel_path = f"{video_folder.name}/{out_clip_path.name}"
            generated_clips.append({
                "clip_index": clip_idx,
                "title": clip_def["title"],
                "filename": out_clip_path.name,
                "file_path": str(out_clip_path),
                "relative_url": f"/output/{clip_rel_path}",
                "start_time": clip_def["start_time"],
                "duration": clip_def["duration"],
                "duration_formatted": format_time(clip_def["duration"]),
                "size_mb": round(out_clip_path.stat().st_size / (1024 * 1024), 2) if out_clip_path.exists() else 0,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "face_follow": face_follow,
                "subtitle_option": subtitle_option,
                "has_srt": has_srt,
                "srt_url": f"/output/{video_folder.name}/{srt_path.name}" if has_srt else None
            })
            job["clips_done"] = idx + 1

        # Combine existing previous clips with newly generated clips
        # Filter duplicates by filename
        seen_filenames = set()
        all_clips = []
        for c in existing_clips + generated_clips:
            fn = c.get("filename")
            if fn and fn not in seen_filenames:
                p_check = video_folder / fn
                if p_check.exists():
                    seen_filenames.add(fn)
                    all_clips.append(c)

        # Re-index nicely
        for i, c in enumerate(all_clips, 1):
            c["clip_index"] = i

        # Step 7: Save Metadata JSON in folder
        job["stage"] = "save"
        job["progress"] = 96
        job["message"] = "Saving clips & metadata to project library..."
        metadata_payload = {
            "video_id": video_id,
            "title": video_title,
            "channel": info["channel"],
            "url": url,
            "thumbnail": info["thumbnail"],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "face_follow": face_follow,
            "subtitle_option": subtitle_option,
            "folder_name": video_folder.name,
            "folder_path": str(video_folder),
            "clips": all_clips
        }
        with open(meta_json_path, "w", encoding="utf-8") as f:
            json.dump(metadata_payload, f, indent=2, ensure_ascii=False)

        job["stage"] = "completed"
        job["progress"] = 100
        job["message"] = f"Successfully created {len(generated_clips)} new clips (Total in project: {len(all_clips)})"
        job["result"] = metadata_payload

    except Exception as e:
        print(f"Job {job_id} error: {e}", file=sys.stderr)
        job["stage"] = "error"
        job["progress"] = 0
        job["message"] = str(e)


@app.post("/api/clip")
@app.post("/api/generate")
async def start_clipping(req: ClipRequest, background_tasks: BackgroundTasks):
    """Initiates an asynchronous clipping process and returns job ID for tracking."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "stage": "starting",
        "progress": 0,
        "message": "Initializing video clipping job...",
        "clips_done": 0,
        "total_clips": req.clip_count,
        "result": None
    }

    background_tasks.add_task(run_clip_job, job_id, req.model_dump())
    return {"success": True, "job_id": job_id}


@app.get("/api/progress/{job_id}")
async def get_job_progress(job_id: str):
    """Server-Sent Events (SSE) stream for real-time progress bar & multi-step status."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        while True:
            job = jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'stage': 'error', 'message': 'Job expired'})}\n\n"
                break

            curr_prog = job.get("progress", 0)
            curr_msg = job.get("message", "")
            curr_stage = job.get("stage", "")

            payload = {
                "stage": curr_stage,
                "progress": curr_prog,
                "message": curr_msg,
                "clips_done": job.get("clips_done", 0),
                "total_clips": job.get("total_clips", 0),
                "result": job.get("result")
            }
            yield f"data: {json.dumps(payload)}\n\n"

            if curr_stage in ["completed", "error"]:
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/library")
async def get_library():
    """Returns all saved video clip folders and their contents, ensuring all historical and newly generated clips are included."""
    library_items = []
    if not OUTPUT_DIR.exists():
        return {"success": True, "items": []}

    for folder in sorted(OUTPUT_DIR.iterdir(), key=lambda p: p.stat().st_mtime if p.is_dir() else 0, reverse=True):
        if not folder.is_dir():
            continue

        # Find all actual mp4 clip files on disk
        mp4_files = sorted(list(folder.glob("clip_*.mp4")), key=lambda p: p.name)
        if not mp4_files:
            continue

        data = None
        meta_file = folder / "metadata.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        if not data:
            data = {
                "video_id": folder.name,
                "title": folder.name,
                "folder_name": folder.name,
                "folder_path": str(folder),
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(folder.stat().st_mtime)),
                "clips": []
            }

        if not data.get("channel"):
            data["channel"] = "YouTube Channel"

        meta_clips = data.get("clips", [])
        meta_clip_by_fn = {c.get("filename"): c for c in meta_clips if c.get("filename")}

        # Reconcile all physical mp4 files with metadata
        all_reconciled_clips = []
        for idx, mp4 in enumerate(mp4_files, 1):
            fn_lower = mp4.name.lower()
            # Detect aspect ratio
            clip_ratio = "9:16"
            if "16x9" in fn_lower:
                clip_ratio = "16:9"
            elif "1x1" in fn_lower:
                clip_ratio = "1:1"
            elif "4x5" in fn_lower:
                clip_ratio = "4:5"
            elif "9x16" in fn_lower:
                clip_ratio = "9:16"
            else:
                clip_ratio = data.get("aspect_ratio", "9:16")

            clip_res = data.get("resolution", "1080p")
            clip_ff = data.get("face_follow", True)

            if mp4.name in meta_clip_by_fn:
                c_obj = meta_clip_by_fn[mp4.name]
                c_obj["clip_index"] = idx
                c_obj["file_path"] = str(mp4)
                c_obj["relative_url"] = f"/output/{folder.name}/{mp4.name}"
                c_obj["aspect_ratio"] = c_obj.get("aspect_ratio") or clip_ratio
                c_obj["resolution"] = c_obj.get("resolution") or clip_res
                c_obj["face_follow"] = c_obj.get("face_follow") if "face_follow" in c_obj else clip_ff
                all_reconciled_clips.append(c_obj)
            else:
                srt_file = mp4.with_suffix(".srt")
                all_reconciled_clips.append({
                    "clip_index": idx,
                    "title": mp4.stem.replace("clip_", "").replace("_", " "),
                    "filename": mp4.name,
                    "file_path": str(mp4),
                    "relative_url": f"/output/{folder.name}/{mp4.name}",
                    "duration_formatted": "Clip",
                    "aspect_ratio": clip_ratio,
                    "resolution": clip_res,
                    "face_follow": clip_ff,
                    "size_mb": round(mp4.stat().st_size / (1024 * 1024), 2),
                    "has_srt": srt_file.exists(),
                    "srt_url": f"/output/{folder.name}/{srt_file.name}" if srt_file.exists() else None
                })

        data["clips"] = all_reconciled_clips
        library_items.append(data)

    return {"success": True, "items": library_items}


@app.post("/api/open-folder")
async def open_in_explorer(req: OpenFolderRequest):
    """Opens a video folder or the main output folder in native Windows Explorer."""
    target_path = OUTPUT_DIR
    if req.folder_path:
        p = Path(req.folder_path)
        if p.exists():
            target_path = p
        else:
            rel = OUTPUT_DIR / req.folder_path
            if rel.exists():
                target_path = rel
    elif req.video_id:
        matching = list(OUTPUT_DIR.glob(f"*_{req.video_id}"))
        if matching:
            target_path = matching[0]

    opened = open_folder(target_path)
    return {"success": opened, "path": str(target_path)}


@app.get("/output/{folder_name}/{filename}")
async def serve_clip_file(folder_name: str, filename: str):
    """Serves video and subtitle files from output directory with range request support."""
    file_path = OUTPUT_DIR / folder_name / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "video/mp4" if filename.endswith(".mp4") else "text/plain"
    return FileResponse(file_path, media_type=media_type, filename=filename)


@app.delete("/api/folder/{folder_name}")
async def delete_folder(folder_name: str):
    """Deletes a video clip folder."""
    target = OUTPUT_DIR / sanitize_filename(folder_name)
    if target.exists() and target.is_dir():
        import shutil
        shutil.rmtree(target, ignore_errors=True)
        return {"success": True, "message": f"Deleted {folder_name}"}
    raise HTTPException(status_code=404, detail="Folder not found")


# ========================================================
# SOCIAL MEDIA AUTH & ONE-CLICK PUBLISHING ENDPOINTS
# ========================================================
from .social.auth_manager import (
    get_public_account_status,
    save_platform_config,
    test_platform_auth
)
from .social.publisher import publish_to_platforms

publish_jobs: Dict[str, Dict[str, Any]] = {}


class SaveSocialAccountRequest(BaseModel):
    platform: str  # 'youtube', 'tiktok', 'instagram'
    credentials: Dict[str, Any]


class TestSocialRequest(BaseModel):
    platform: str
    token: Optional[str] = None


class PublishClipRequest(BaseModel):
    file_path: str
    title: str
    description: Optional[str] = ""
    tags: Optional[List[str]] = None
    platforms: List[str]  # e.g. ['youtube', 'tiktok', 'instagram']
    options: Optional[Dict[str, Any]] = None


@app.get("/api/social/accounts")
async def get_social_accounts():
    """Returns connected status and profile handles for social platforms."""
    status = get_public_account_status()
    return {"success": True, "accounts": status}


@app.post("/api/social/accounts")
async def update_social_account(req: SaveSocialAccountRequest):
    """Saves API credentials or tokens for a social platform."""
    updated = save_platform_config(req.platform, req.credentials)
    return {"success": True, "accounts": updated}


@app.post("/api/social/test")
async def test_social_account(req: TestSocialRequest):
    """Tests live connection to a social media platform API using saved or provided token."""
    result = test_platform_auth(req.platform, token=req.token)
    return result


@app.post("/api/social/refresh")
async def force_refresh_social_token(req: TestSocialRequest):
    """Forces an immediate OAuth token renewal using saved refresh credentials."""
    from .social.auth_manager import refresh_youtube_access_token, refresh_tiktok_access_token
    if req.platform == "youtube":
        new_token = refresh_youtube_access_token()
        if new_token:
            test_res = test_platform_auth("youtube")
            return {
                "success": True,
                "token": new_token,
                "message": f"Successfully renewed YouTube Access Token! ({test_res.get('message', '')})"
            }
        else:
            return {
                "success": False,
                "message": "Failed to refresh YouTube token. Google rejected the refresh request (invalid_grant). If using a personal test project, make sure the OAuth consent screen is set to 'In Production' so refresh tokens don't expire after 7 days."
            }
    elif req.platform == "tiktok":
        new_token = refresh_tiktok_access_token()
        if new_token:
            test_res = test_platform_auth("tiktok")
            return {
                "success": True,
                "token": new_token,
                "message": f"Successfully renewed TikTok Access Token! ({test_res.get('message', '')})"
            }
        else:
            return {
                "success": False,
                "message": "Failed to refresh TikTok token. Verify your Client Key, Client Secret, and Refresh Token."
            }
    elif req.platform == "instagram":
        from .social.auth_manager import refresh_instagram_access_token
        new_token = refresh_instagram_access_token()
        if new_token:
            test_res = test_platform_auth("instagram")
            return {
                "success": True,
                "token": new_token,
                "message": f"Successfully renewed Instagram Access Token! ({test_res.get('message', '')})"
            }
        else:
            return {
                "success": False,
                "message": "Failed to renew Instagram token. Ensure Meta App ID, App Secret, and a valid base token are saved."
            }
    return {"success": False, "message": "Refresh not supported for this platform."}


@app.get("/oauth2callback")
async def oauth2_callback(code: Optional[str] = None, error: Optional[str] = None):
    """Handles Google OAuth2 callback redirect."""
    if error:
        return HTMLResponse(f"<h3>Google Authentication Cancelled: {error}</h3>")
    if not code:
        return HTMLResponse("<h3>No authorization code received.</h3>")

    from .social.auth_manager import get_social_config, save_platform_config
    config = get_social_config()
    yt = config.get("youtube", {})
    client_id = yt.get("client_id", "").strip()
    client_secret = yt.get("client_secret", "").strip()

    if client_id and client_secret:
        import requests
        try:
            token_res = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": "http://localhost:8000/oauth2callback",
                    "grant_type": "authorization_code"
                },
                timeout=15
            )
            if token_res.status_code == 200:
                td = token_res.json()
                yt["access_token"] = td.get("access_token", "")
                if td.get("refresh_token"):
                    yt["refresh_token"] = td.get("refresh_token")
                yt["connected"] = True
                save_platform_config("youtube", yt)
                return HTMLResponse("""
                    <body style="background:#0B0F17;color:#00E1B4;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;">
                        <h2>✅ YouTube Connected Successfully!</h2>
                        <p style="color:#94A3B8;">Tokens saved. You can close this window now.</p>
                        <script>
                            if (window.opener) { window.opener.location.reload(); }
                            setTimeout(() => window.close(), 2000);
                        </script>
                    </body>
                """)
        except Exception:
            pass

    return HTMLResponse(f"""
        <body style="background:#0B0F17;color:#fff;font-family:sans-serif;padding:30px;">
            <h3>Google Authorization Code Received</h3>
            <p>Code: <code>{code}</code></p>
            <p><a href="/" style="color:#00E1B4;">Return to YouTube Clipper</a></p>
        </body>
    """)


from .social.history_manager import (
    get_post_history,
    add_post_history_entry,
    delete_history_entry,
    clear_all_history
)


def run_social_publish_job(job_id: str, req_data: Dict[str, Any]):
    """Background worker for multi-platform publishing."""
    job = publish_jobs[job_id]
    try:
        job["status"] = "uploading"
        job["message"] = f"Publishing to {len(req_data.get('platforms', []))} platforms..."
        
        res = publish_to_platforms(
            video_path=req_data["file_path"],
            title=req_data["title"],
            description=req_data.get("description", ""),
            tags=req_data.get("tags"),
            platforms=req_data.get("platforms"),
            options=req_data.get("options")
        )

        job["status"] = "completed" if res.get("success") else "failed"
        job["message"] = "Multi-platform publishing completed."
        job["results"] = res.get("results", {})
        job["success"] = res.get("success", False)

        # Save to persistent history (retains across refreshes/restarts)
        add_post_history_entry(
            title=req_data["title"],
            file_path=req_data["file_path"],
            platforms=req_data.get("platforms", []),
            results=res.get("results", {}),
            description=req_data.get("description", ""),
            options=req_data.get("options")
        )
    except Exception as e:
        job["status"] = "error"
        job["message"] = str(e)
        job["success"] = False


@app.post("/api/social/publish")
async def publish_clip(req: PublishClipRequest, background_tasks: BackgroundTasks):
    """Starts one-click publish job to selected social platforms."""
    # Resolve file path
    target_path = Path(req.file_path)
    if not target_path.exists():
        # Try relative to output dir
        cand = OUTPUT_DIR / req.file_path.replace("/output/", "").lstrip("/")
        if cand.exists():
            target_path = cand
        else:
            raise HTTPException(status_code=404, detail=f"Clip file not found: {req.file_path}")

    job_id = str(uuid.uuid4())
    publish_jobs[job_id] = {
        "job_id": job_id,
        "status": "starting",
        "message": "Initializing multi-platform upload...",
        "platforms": req.platforms,
        "results": {},
        "success": None
    }

    payload = req.model_dump()
    payload["file_path"] = str(target_path)
    background_tasks.add_task(run_social_publish_job, job_id, payload)

    return {"success": True, "job_id": job_id}


@app.get("/api/social/publish-status/{job_id}")
async def get_publish_status(job_id: str):
    """Retrieves status of active multi-platform publish job."""
    if job_id not in publish_jobs:
        raise HTTPException(status_code=404, detail="Publish job not found")
    return publish_jobs[job_id]


@app.get("/api/social/history")
async def get_history():
    """Returns persistent post publishing history."""
    history = get_post_history()
    return {"success": True, "history": history}


@app.delete("/api/social/history/{item_id}")
async def delete_history_item(item_id: str):
    """Deletes a specific post history entry."""
    success = delete_history_entry(item_id)
    return {"success": success}


@app.delete("/api/social/history")
async def clear_history():
    """Clears all post publishing history."""
    success = clear_all_history()
    return {"success": success}


# ==========================================================
# AUTO-PILOT DAILY TRENDING & SOCIAL PUBLISHING ENDPOINTS
# ==========================================================

class AutopilotConfigRequest(BaseModel):
    enabled: bool = False
    schedule_time: str = "09:00"
    countries: List[str] = ["US"]
    category: str = "all"
    max_videos_per_run: int = 3
    clip_preferences: Dict[str, Any] = Field(default_factory=dict)
    upload_targets: Dict[str, bool] = Field(default_factory=dict)
    privacy_status: str = "public"
    auto_publish_mode: str = "auto_upload"
    title_template: str = "{clip_title} #shorts #trending"
    description_template: str = "🔥 Trending viral moment from {video_title} by {channel}.\n\n#shorts #trending #{country_code} #viral"


@app.get("/api/autopilot/config")
async def get_autopilot_config():
    """Retrieves current Auto-Pilot daily configuration and supported country options."""
    config = load_autopilot_config()
    country_options = [
        {"code": code, "name": name, "flag": COUNTRY_EMOJIS.get(code, "🌐")}
        for code, name in COUNTRY_MAP.items()
    ]
    return {
        "success": True,
        "config": config,
        "country_options": country_options
    }


@app.post("/api/autopilot/config")
async def update_autopilot_config(req: AutopilotConfigRequest):
    """Saves updated Auto-Pilot settings."""
    payload = req.model_dump()
    saved = save_autopilot_config(payload)
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to save Auto-Pilot configuration.")
    return {"success": True, "config": payload, "status": autopilot_engine.get_status()}


@app.get("/api/autopilot/status")
async def get_autopilot_status():
    """Gets live heartbeat and execution state of the Auto-Pilot scheduler."""
    status = autopilot_engine.get_status()
    return {"success": True, "status": status}


@app.post("/api/autopilot/trigger")
async def trigger_autopilot_manual(background_tasks: BackgroundTasks):
    """Manually triggers an immediate Auto-Pilot scraping, clipping, and auto-publishing run."""
    if autopilot_engine.is_executing:
        return {"success": False, "message": "An Auto-Pilot job is already actively executing."}

    background_tasks.add_task(autopilot_engine.run_autopilot_pipeline, "manual")
    return {
        "success": True,
        "message": "⚡ Auto-Pilot pipeline started in background!",
        "status": autopilot_engine.get_status()
    }


@app.get("/api/autopilot/history")
async def get_autopilot_history():
    """Retrieves history of past Auto-Pilot automated runs."""
    history = load_autopilot_history()
    return {"success": True, "history": history}


@app.post("/api/autopilot/clear-history")
async def clear_autopilot_run_history():
    """Clears past Auto-Pilot run execution logs."""
    cleared = clear_autopilot_history()
    return {"success": cleared}


