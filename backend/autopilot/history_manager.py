import json
import time
from pathlib import Path
from typing import Dict, Any, List, Set, Optional

HISTORY_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "autopilot_history.json"


def load_autopilot_history() -> Dict[str, Any]:
    """Loads past auto-pilot execution history and processed video records."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        initial = {"runs": [], "processed_video_ids": []}
        save_autopilot_history(initial)
        return initial

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "runs" not in data:
                data["runs"] = []
            if "processed_video_ids" not in data:
                data["processed_video_ids"] = []
            return data
    except Exception as err:
        print(f"Warning: Failed to load autopilot history: {err}")
        return {"runs": [], "processed_video_ids": []}


def save_autopilot_history(history: Dict[str, Any]) -> bool:
    """Saves updated history to disk."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        return True
    except Exception as err:
        print(f"Error saving autopilot history: {err}")
        return False


def get_processed_video_ids() -> Set[str]:
    """Returns a set of all video IDs previously processed by auto-pilot."""
    history = load_autopilot_history()
    return set(history.get("processed_video_ids", []))


def add_autopilot_run_entry(run_entry: Dict[str, Any]) -> None:
    """Appends a completed auto-pilot run record and updates deduplication IDs."""
    history = load_autopilot_history()
    runs = history.get("runs", [])
    processed_ids = set(history.get("processed_video_ids", []))

    # Add new video IDs to deduplication pool
    for v in run_entry.get("videos_processed", []):
        vid = v.get("video_id")
        if vid:
            processed_ids.add(vid)

    # Keep latest 50 runs in history
    runs.insert(0, run_entry)
    history["runs"] = runs[:50]
    history["processed_video_ids"] = list(processed_ids)
    save_autopilot_history(history)


def clear_autopilot_history() -> bool:
    """Clears past execution history logs while preserving deduplication IDs."""
    history = load_autopilot_history()
    history["runs"] = []
    return save_autopilot_history(history)
