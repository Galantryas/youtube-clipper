import os
import re
import sys
import shutil
import platform
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str, max_length: int = 60) -> str:
    """Sanitizes a string to make it safe for filesystem directories and file names."""
    if not name:
        return "untitled"
    # Remove invalid characters for Windows/Linux
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    # Replace multiple spaces/dashes with single space/underscore
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"[^\w\-_.]", "", cleaned)
    cleaned = cleaned.strip(" ._-")
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" ._-")
    return cleaned or "video"


def get_ffmpeg_path() -> str:
    """Finds FFmpeg executable path from system or imageio_ffmpeg."""
    # Check if ffmpeg is in PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    # Check imageio_ffmpeg
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_exe and os.path.exists(ffmpeg_exe):
            return ffmpeg_exe
    except Exception:
        pass

    # Check local bin
    local_bin = BASE_DIR / "bin" / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
    if local_bin.exists():
        return str(local_bin)

    return "ffmpeg"


def get_output_dir(video_title: str, video_id: str) -> Path:
    """Creates and returns the dedicated directory for a specific YouTube video."""
    folder_name = f"{sanitize_filename(video_title)}_{sanitize_filename(video_id)}"
    target_path = OUTPUT_DIR / folder_name
    target_path.mkdir(parents=True, exist_ok=True)
    return target_path


def open_folder(target_path: str | Path) -> bool:
    """Opens a folder in the native OS file explorer (Windows Explorer, macOS Finder, Linux)."""
    p = Path(target_path).resolve()
    if not p.exists():
        return False

    current_os = platform.system()
    try:
        if current_os == "Windows":
            if p.is_file():
                subprocess.Popen(f'explorer /select,"{p}"')
            else:
                os.startfile(str(p))
            return True
        elif current_os == "Darwin":  # macOS
            subprocess.Popen(["open", str(p)])
            return True
        else:  # Linux
            subprocess.Popen(["xdg-open", str(p)])
            return True
    except Exception as e:
        print(f"Error opening folder: {e}")
        return False


def format_time(seconds: float) -> str:
    """Formats seconds to HH:MM:SS or MM:SS."""
    seconds = int(seconds)
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"
