import os
import re
import warnings

# Suppress upstream library deprecation notices
warnings.filterwarnings("ignore", message=".*Deprecated Feature.*")
warnings.filterwarnings("ignore", message=".*deprecated.*")

import yt_dlp
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from .utils import sanitize_filename, format_time, get_ffmpeg_path, TEMP_DIR


def extract_video_id(url: str) -> Optional[str]:
    """Extracts YouTube video ID from various URL formats."""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
        r"(?:embed\/)([0-9A-Za-z_-]{11})",
        r"(?:shorts\/)([0-9A-Za-z_-]{11})",
        r"^([0-9A-Za-z_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    return None


def get_video_info(url: str) -> Dict[str, Any]:
    """Fetches comprehensive metadata for a given YouTube URL."""
    video_id = extract_video_id(url)
    if not video_id:
        normalized_url = url
    else:
        normalized_url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "nocheckcertificate": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web_creator", "web"]
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(normalized_url, download=False)
        except Exception as e:
            raise ValueError(f"Failed to fetch YouTube video info: {str(e)}")

    if not info:
        raise ValueError("Could not retrieve video information.")

    # Extract available video heights
    resolutions = set()
    formats = info.get("formats", [])
    for f in formats:
        height = f.get("height")
        if height and isinstance(height, int) and height >= 144:
            resolutions.add(f"{height}p")

    # Sort resolutions numerically
    sorted_resolutions = sorted(
        list(resolutions),
        key=lambda r: int(r.replace("p", "")) if r.replace("p", "").isdigit() else 0,
        reverse=True
    )
    if not sorted_resolutions:
        sorted_resolutions = ["1080p", "720p", "480p", "360p"]

    # Extract chapters if any
    chapters = []
    for ch in info.get("chapters") or []:
        chapters.append({
            "title": ch.get("title", "Chapter"),
            "start_time": ch.get("start_time", 0),
            "end_time": ch.get("end_time", 0),
            "duration": ch.get("end_time", 0) - ch.get("start_time", 0),
            "start_formatted": format_time(ch.get("start_time", 0)),
            "end_formatted": format_time(ch.get("end_time", 0)),
        })

    # Subtitles list
    subtitles = list((info.get("subtitles") or {}).keys()) + list((info.get("automatic_captions") or {}).keys())
    unique_subtitles = sorted(list(set(subtitles)))

    duration_sec = info.get("duration", 0) or 0

    return {
        "id": info.get("id", video_id or "unknown"),
        "url": normalized_url,
        "title": info.get("title", "Untitled Video"),
        "channel": info.get("uploader") or info.get("channel", "Unknown Channel"),
        "channel_url": info.get("uploader_url") or info.get("channel_url", ""),
        "duration": duration_sec,
        "duration_formatted": format_time(duration_sec),
        "thumbnail": info.get("thumbnail") or f"https://img.youtube.com/vi/{info.get('id')}/hqdefault.jpg",
        "description": (info.get("description") or "")[:400],
        "view_count": info.get("view_count", 0),
        "available_resolutions": sorted_resolutions,
        "subtitles_available": unique_subtitles[:10],
        "chapters": chapters,
    }


def download_source_video(
    url: str,
    output_filepath: str | Path,
    target_res: str = "1080p",
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
) -> Path:
    """Downloads highest quality video + audio up to target_res and saves to output_filepath."""
    output_path = Path(output_filepath)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg_path()

    max_height = 1080
    if target_res and target_res.endswith("p"):
        try:
            max_height = int(target_res.replace("p", ""))
        except ValueError:
            max_height = 1080

    def ydl_progress_hook(d):
        if not progress_callback:
            return
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            downloaded = d.get("downloaded_bytes", 0)
            percent = min(100.0, max(0.0, (downloaded / total) * 100))
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0
            progress_callback({
                "status": "downloading",
                "percent": percent,
                "speed_mb": round(speed / (1024 * 1024), 2) if speed else 0,
                "eta_sec": eta,
                "message": f"Downloading video... {percent:.1f}% ({round(downloaded / (1024 * 1024), 1)} MB)"
            })
        elif status == "finished":
            progress_callback({
                "status": "merging",
                "percent": 100.0,
                "message": "Download finished. Merging audio & video streams..."
            })

    format_spec = f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}][ext=mp4]/best[height<={max_height}]/best"

    primary_opts = {
        "format": format_spec,
        "outtmpl": str(output_path.with_suffix("")) + ".%(ext)s",
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_exe,
        "progress_hooks": [ydl_progress_hook],
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
        "nocheckcertificate": True,
        "retries": 10,
        "fragment_retries": 10,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web_creator", "mweb", "web"]
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
    }

    try:
        with yt_dlp.YoutubeDL(primary_opts) as ydl:
            ydl.download([url])
    except Exception as primary_err:
        print(f"Notice: Primary download encountered: {primary_err}. Attempting mobile client fallback...")
        if progress_callback:
            progress_callback({
                "status": "downloading",
                "percent": 10.0,
                "message": "Switching to high-compatibility stream client..."
            })

        # Fallback options targeting Android/iOS client stream
        fallback_opts = {
            "format": f"best[height<={max_height}]/bestvideo+bestaudio/best",
            "outtmpl": str(output_path.with_suffix("")) + ".%(ext)s",
            "merge_output_format": "mp4",
            "ffmpeg_location": ffmpeg_exe,
            "progress_hooks": [ydl_progress_hook],
            "quiet": True,
            "no_warnings": True,
            "overwrites": True,
            "nocheckcertificate": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["ios", "android_creator", "android"]
                }
            },
            "http_headers": {
                "User-Agent": "com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X; en_US)",
                "Accept-Language": "en-US,en;q=0.9",
            }
        }
        with yt_dlp.YoutubeDL(fallback_opts) as ydl:
            ydl.download([url])

    if output_path.exists() and output_path.stat().st_size > 1000:
        return output_path
    
    mp4_target = output_path.with_suffix(".mp4")
    if mp4_target.exists() and mp4_target.stat().st_size > 1000:
        return mp4_target

    stem = output_path.stem
    matching = [f for f in output_path.parent.glob(f"{stem}*") if f.is_file() and f.stat().st_size > 1000]
    if matching:
        target = matching[0]
        if target != output_path and target.suffix.lower() != ".mp4" and output_path.suffix.lower() == ".mp4":
            try:
                target.rename(output_path)
                return output_path
            except Exception:
                pass
        return target

    raise FileNotFoundError(f"Downloaded video not found at {output_path}")
