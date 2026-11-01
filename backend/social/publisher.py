import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional

from .youtube_publisher import upload_to_youtube
from .tiktok_publisher import upload_to_tiktok
from .instagram_publisher import upload_to_instagram


def publish_to_platforms(
    video_path: str | Path,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Orchestrates concurrent video uploads across chosen social media platforms.
    platforms: e.g. ['youtube', 'tiktok', 'instagram']
    """
    if not platforms:
        return {"success": False, "error": "No social platforms selected for publishing."}

    if options is None:
        options = {}

    results = {}
    p = Path(video_path)

    if not p.exists():
        return {"success": False, "error": f"Video file not found: {video_path}"}

    def run_single_upload(platform: str):
        if platform == "youtube":
            privacy = options.get("youtube_privacy", "public")
            return "youtube", upload_to_youtube(
                video_path=p,
                title=title,
                description=description,
                tags=tags,
                privacy_status=privacy
            )
        elif platform == "tiktok":
            privacy_level = options.get("tiktok_privacy", "PUBLIC_TO_EVERYONE")
            disable_comment = options.get("tiktok_disable_comment", False)
            disable_duet = options.get("tiktok_disable_duet", False)
            return "tiktok", upload_to_tiktok(
                video_path=p,
                title=title,
                privacy_level=privacy_level,
                disable_comment=disable_comment,
                disable_duet=disable_duet
            )
        elif platform == "instagram":
            share_to_feed = options.get("instagram_share_feed", True)
            return "instagram", upload_to_instagram(
                video_path=p,
                caption=f"{title}\n\n{description}".strip(),
                share_to_feed=share_to_feed
            )
        else:
            return platform, {"success": False, "error": f"Unsupported platform: {platform}"}

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run_single_upload, plat.lower().strip()) for plat in platforms]
        for future in as_completed(futures):
            try:
                plat_name, res = future.result()
                results[plat_name] = res
            except Exception as e:
                results[plat_name] = {"success": False, "error": str(e)}

    # Overall success if at least one platform succeeded
    any_success = any(r.get("success") for r in results.values())

    return {
        "success": any_success,
        "results": results
    }
