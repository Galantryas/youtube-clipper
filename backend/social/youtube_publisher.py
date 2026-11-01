import os
import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from .auth_manager import get_social_config, get_youtube_valid_token


def upload_to_youtube(
    video_path: str | Path,
    title: str,
    description: str = "",
    tags: Optional[list] = None,
    privacy_status: str = "public"
) -> Dict[str, Any]:
    """Uploads a video to YouTube / YouTube Shorts using YouTube Data API v3 with automatic token refresh."""
    token = get_youtube_valid_token()

    if not token:
        return {
            "success": False,
            "error": "YouTube Access Token is missing or expired. Please check YouTube settings in Social Accounts."
        }

    p = Path(video_path)
    if not p.exists():
        return {"success": False, "error": f"Video file not found at {video_path}"}

    file_size = p.stat().st_size
    if tags is None:
        tags = ["Shorts", "Viral", "YouTubeClipper"]

    # Clean user title and description without promotional additions
    final_title = title[:100]
    final_desc = description.strip()

    metadata = {
        "snippet": {
            "title": final_title,
            "description": final_desc,
            "tags": tags[:15],
            "categoryId": "22"  # People & Blogs
        },
        "status": {
            "privacyStatus": privacy_status,  # public, unlisted, private
            "selfDeclaredMadeForKids": False
        }
    }

    try:
        # Step 1: Initiate resumable upload session
        init_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(file_size),
            "X-Upload-Content-Type": "video/mp4"
        }

        init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
        init_res = requests.post(init_url, headers=init_headers, json=metadata, timeout=15)

        if init_res.status_code != 200:
            return {
                "success": False,
                "error": f"YouTube init upload failed ({init_res.status_code}): {init_res.text[:150]}"
            }

        upload_url = init_res.headers.get("Location")
        if not upload_url:
            return {"success": False, "error": "YouTube did not return upload location URL."}

        # Step 2: Upload the binary video content
        with open(p, "rb") as f:
            video_bytes = f.read()

        upload_headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(file_size)
        }

        upload_res = requests.put(upload_url, headers=upload_headers, data=video_bytes, timeout=120)

        if upload_res.status_code in [200, 201]:
            resp_data = upload_res.json()
            video_id = resp_data.get("id")
            return {
                "success": True,
                "video_id": video_id,
                "url": f"https://youtube.com/shorts/{video_id}",
                "message": f"Successfully published to YouTube Shorts: https://youtube.com/shorts/{video_id}"
            }
        else:
            return {
                "success": False,
                "error": f"YouTube upload failed ({upload_res.status_code}): {upload_res.text[:150]}"
            }

    except Exception as e:
        return {"success": False, "error": f"YouTube upload error: {str(e)}"}
