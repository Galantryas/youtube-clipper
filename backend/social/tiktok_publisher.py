import os
import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from .auth_manager import get_social_config, get_tiktok_valid_token


def upload_to_tiktok(
    video_path: str | Path,
    title: str,
    privacy_level: str = "PUBLIC_TO_EVERYONE",  # PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, SELF_ONLY
    disable_comment: bool = False,
    disable_duet: bool = False
) -> Dict[str, Any]:
    """Uploads a video to TikTok using TikTok Content Posting API v2."""
    token = get_tiktok_valid_token()

    if not token:
        return {
            "success": False,
            "error": "TikTok Access Token is missing or expired. Please configure TikTok in Social Accounts settings."
        }

    p = Path(video_path)
    if not p.exists():
        return {"success": False, "error": f"Video file not found at {video_path}"}

    file_size = p.stat().st_size

    final_caption = title.strip()[:150]

    payload = {
        "post_info": {
            "title": final_caption,
            "privacy_level": privacy_level,
            "disable_comment": disable_comment,
            "disable_duet": disable_duet,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": file_size,
            "total_chunk_count": 1
        }
    }

    try:
        # Step 1: Initialize TikTok Direct Post
        init_res = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8"
            },
            json=payload,
            timeout=15
        )

        if init_res.status_code != 200:
            return {
                "success": False,
                "error": f"TikTok post init failed ({init_res.status_code}): {init_res.text[:150]}"
            }

        res_json = init_res.json()
        data = res_json.get("data", {})
        upload_url = data.get("upload_url")
        publish_id = data.get("publish_id")

        if not upload_url:
            err_msg = res_json.get("error", {}).get("message") or "No upload URL returned by TikTok."
            return {"success": False, "error": f"TikTok error: {err_msg}"}

        # Step 2: Upload Video File Content
        with open(p, "rb") as f:
            video_bytes = f.read()

        put_headers = {
            "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
            "Content-Type": "video/mp4"
        }

        upload_res = requests.put(upload_url, headers=put_headers, data=video_bytes, timeout=120)

        if upload_res.status_code in [200, 201, 206]:
            return {
                "success": True,
                "publish_id": publish_id,
                "message": "Successfully published video to TikTok!"
            }
        else:
            return {
                "success": False,
                "error": f"TikTok upload binary failed ({upload_res.status_code}): {upload_res.text[:150]}"
            }

    except Exception as e:
        return {"success": False, "error": f"TikTok upload error: {str(e)}"}
