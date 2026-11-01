import os
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
HISTORY_FILE = CONFIG_DIR / "post_history.json"


def init_history():
    """Initializes the post history file if it does not exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def get_post_history() -> List[Dict[str, Any]]:
    """Returns all saved post history records (newest first)."""
    init_history()
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def add_post_history_entry(
    title: str,
    file_path: str,
    platforms: List[str],
    results: Dict[str, Any],
    description: str = "",
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Adds a new publishing record to persistent post history."""
    init_history()
    history = get_post_history()

    p = Path(file_path)
    filename = p.name if p.exists() else Path(file_path).name

    # Determine overall status
    any_success = any(r.get("success") for r in results.values()) if results else False

    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "title": title,
        "description": description,
        "filename": filename,
        "file_path": str(file_path),
        "platforms": platforms,
        "results": results,
        "success": any_success,
        "options": options or {}
    }

    # Prepend newest record
    history.insert(0, entry)

    # Keep up to 200 history entries
    history = history[:200]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    return entry


def delete_history_entry(item_id: str) -> bool:
    """Deletes a specific history record by ID."""
    init_history()
    history = get_post_history()
    new_history = [item for item in history if item.get("id") != item_id]
    if len(new_history) != len(history):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(new_history, f, indent=2, ensure_ascii=False)
        return True
    return False


def clear_all_history() -> bool:
    """Clears all post history."""
    init_history()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)
    return True
