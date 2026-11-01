import os
import time
import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from .auth_manager import get_social_config, get_instagram_valid_token


def upload_to_instagram(
    video_path: str | Path,
    caption: str,
    share_to_feed: bool = True
) -> Dict[str, Any]:
    """Uploads and publishes a video as Instagram Reels using Instagram Graph API."""
    config = get_social_config()
    creds = config.get("instagram", {})
    token = get_instagram_valid_token() or creds.get("access_token", "").strip()
    account_id = creds.get("instagram_account_id", "").strip()

    if not token or not account_id:
        return {
            "success": False,
            "error": "Instagram Access Token or Account ID is missing or expired. Please configure Instagram in Social Accounts settings."
        }

    p = Path(video_path)
    if not p.exists():
        return {"success": False, "error": f"Video file not found at {video_path}"}

    file_size = p.stat().st_size
    final_caption = caption.strip()[:2200]

    try:
        # Step 1: Create Reel Container with Resumable Upload
        init_url = f"https://graph.facebook.com/v19.0/{account_id}/media"
        init_params = {
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": final_caption[:2200],
            "share_to_feed": str(share_to_feed).lower(),
            "access_token": token
        }

        init_res = requests.post(init_url, data=init_params, timeout=15)
        if init_res.status_code != 200:
            return {
                "success": False,
                "error": f"Instagram container creation failed ({init_res.status_code}): {init_res.text[:150]}"
            }

        init_data = init_res.json()
        container_id = init_data.get("id")
        upload_url = init_data.get("uri")

        if not upload_url or not container_id:
            return {"success": False, "error": "Instagram did not return upload URI."}

        # Step 2: Upload Video Binary to Resumable Session
        with open(p, "rb") as f:
            video_bytes = f.read()

        upload_headers = {
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(file_size)
        }

        upload_res = requests.post(upload_url, headers=upload_headers, data=video_bytes, timeout=120)
        if upload_res.status_code not in [200, 201]:
            return {
                "success": False,
                "error": f"Instagram binary upload failed ({upload_res.status_code}): {upload_res.text[:150]}"
            }

        # Step 3: Wait for Instagram video processing and publish
        # Polling status of container
        for _ in range(12):
            status_res = requests.get(
                f"https://graph.facebook.com/v19.0/{container_id}",
                params={"fields": "status_code", "access_token": token},
                timeout=10
            )
            if status_res.status_code == 200:
                sc = status_res.json().get("status_code")
                if sc == "FINISHED":
                    break
                elif sc == "ERROR":
                    return {"success": False, "error": "Instagram video processing failed."}
            time.sleep(2)

        # Step 4: Media Publish
        publish_url = f"https://graph.facebook.com/v19.0/{account_id}/media_publish"
        publish_res = requests.post(
            publish_url,
            data={"creation_id": container_id, "access_token": token},
            timeout=15
        )

        if publish_res.status_code == 200:
            media_id = publish_res.json().get("id")
            return {
                "success": True,
                "media_id": media_id,
                "message": "Successfully published Reel to Instagram!"
            }
        else:
            return {
                "success": False,
                "error": f"Instagram publish failed ({publish_res.status_code}): {publish_res.text[:150]}"
            }

    except Exception as e:
        return {"success": False, "error": f"Instagram upload error: {str(e)}"}
