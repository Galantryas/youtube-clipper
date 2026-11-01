import json
from pathlib import Path
from typing import Dict, Any, List

CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "autopilot_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "schedule_time": "09:00",  # 24-hour format HH:MM
    "countries": ["US", "ID"],
    "category": "all",  # "all", "gaming", "entertainment", "news", "tech", "music"
    "max_videos_per_run": 3,
    "clip_preferences": {
        "aspect_ratio": "9:16",
        "resolution": "1080p",
        "clip_count": 2,
        "target_duration": 30.0,
        "face_follow": "single",
        "subtitle_option": "tiktok",
    },
    "upload_targets": {
        "youtube": True,
        "tiktok": False,
        "instagram": False,
    },
    "privacy_status": "public",  # "public", "unlisted", "private"
    "auto_publish_mode": "auto_upload",  # "auto_upload" or "draft_only"
    "title_template": "{clip_title} #shorts #trending",
    "description_template": "🔥 Trending viral moment from {video_title} by {channel}.\n\n#shorts #trending #{country_code} #viral",
}


def load_autopilot_config() -> Dict[str, Any]:
    """Loads current autopilot configuration or returns defaults."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_autopilot_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with defaults for schema evolution
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            if "clip_preferences" in data and isinstance(data["clip_preferences"], dict):
                merged["clip_preferences"] = {**DEFAULT_CONFIG["clip_preferences"], **data["clip_preferences"]}
            if "upload_targets" in data and isinstance(data["upload_targets"], dict):
                merged["upload_targets"] = {**DEFAULT_CONFIG["upload_targets"], **data["upload_targets"]}
            return merged
    except Exception as err:
        print(f"Warning: Failed reading autopilot config: {err}. Returning default config.")
        return DEFAULT_CONFIG.copy()


def save_autopilot_config(config: Dict[str, Any]) -> bool:
    """Saves updated autopilot configuration to disk."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as err:
        print(f"Error saving autopilot config: {err}")
        return False
