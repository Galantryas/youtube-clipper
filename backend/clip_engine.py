import os
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from .utils import get_ffmpeg_path, format_time, sanitize_filename
from .face_tracker import FaceTracker
from .subtitle_engine import generate_styled_ass, generate_clip_srt


def get_video_dimensions(video_path: Path, ffmpeg_exe: str) -> tuple[int, int]:
    """Gets video width and height using ffprobe or ffmpeg."""
    # Default fallback
    width, height = 1920, 1080
    
    # Try using ffprobe if available alongside ffmpeg
    probe_exe = ffmpeg_exe.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
    if os.path.exists(probe_exe):
        try:
            cmd = [
                probe_exe,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                str(video_path)
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                streams = data.get("streams", [])
                if streams:
                    return int(streams[0]["width"]), int(streams[0]["height"])
        except Exception:
            pass

    # OpenCV fallback
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            if w > 0 and h > 0:
                return w, h
    except Exception:
        pass

    return width, height


def get_target_resolution(aspect_ratio: str, resolution_quality: str) -> tuple[int, int]:
    """Calculates output (width, height) based on chosen ratio and resolution preset."""
    # Base height presets
    quality_map = {
        "720p": 720,
        "1080p": 1080,
        "1440p": 1440,
        "4k": 2160,
    }
    base_dim = quality_map.get(resolution_quality.lower(), 1080)

    if aspect_ratio == "9:16":
        # Vertical (Shorts/TikTok)
        if base_dim == 720:
            return 720, 1280
        elif base_dim == 2160:
            return 2160, 3840
        else:
            return 1080, 1920
    elif aspect_ratio == "1:1":
        # Square
        return base_dim, base_dim
    elif aspect_ratio == "4:5":
        # Portrait (Instagram)
        target_w = base_dim
        target_h = int(base_dim * 5 / 4)
        # Ensure even numbers
        return (target_w // 2) * 2, (target_h // 2) * 2
    else:
        # 16:9 Landscape
        if base_dim == 720:
            return 1280, 720
        elif base_dim == 2160:
            return 3840, 2160
        else:
            return 1920, 1080


def escape_ffmpeg_path(path: str | Path) -> str:
    """Escapes file paths for FFmpeg filtergraph on Windows & Unix."""
    p_str = str(Path(path).resolve()).replace("\\", "/")
    # Escape colon for Windows drive letters like C:/
    p_str = p_str.replace(":", "\\:")
    # Escape single quotes and brackets
    p_str = p_str.replace("'", "'\\\\\\''")
    p_str = p_str.replace("[", "\\[").replace("]", "\\]")
    return p_str


def process_single_clip(
    source_video_path: Path,
    output_clip_path: Path,
    start_time: float,
    duration: float,
    aspect_ratio: str = "9:16",
    resolution: str = "1080p",
    face_follow: bool = True,
    background_mode: str = "crop",  # 'crop' or 'blur'
    subtitle_option: str = "tiktok",  # 'none', 'tiktok', 'clean', 'srt_only'
    transcript: Optional[List[Dict[str, Any]]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Path:
    """
    Renders an individual clip with chosen aspect ratio, face tracking, and styled subtitles.
    """
    ffmpeg_exe = get_ffmpeg_path()
    output_clip_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = output_clip_path.parent / "temp_clips"
    temp_dir.mkdir(parents=True, exist_ok=True)

    target_w, target_h = get_target_resolution(aspect_ratio, resolution)
    orig_w, orig_h = get_video_dimensions(source_video_path, ffmpeg_exe)

    if progress_callback:
        progress_callback({"percent": 20, "message": "Analyzing framing & crop..."})

    # Prepare subtitle file if requested
    subtitle_ass_path = None
    if subtitle_option in ["tiktok", "clean"] and transcript:
        ass_file = temp_dir / f"{output_clip_path.stem}_sub.ass"
        is_vert = aspect_ratio in ["9:16", "4:5", "1:1"]
        subtitle_ass_path = generate_styled_ass(
            transcript=transcript,
            clip_start=start_time,
            clip_duration=duration,
            output_path=ass_file,
            style_type=subtitle_option,
            is_vertical=is_vert
        )

    # Parse face tracking mode
    ff_mode = "single"
    if isinstance(face_follow, bool):
        ff_mode = "single" if face_follow else "none"
    elif isinstance(face_follow, str):
        ff_mode = face_follow.lower().strip()
    if ff_mode not in ["single", "dynamic", "split", "none"]:
        ff_mode = "single"

    # Check if split-screen mode is requested for vertical 9:16
    is_split_screen = (aspect_ratio == "9:16" and ff_mode == "split")
    split_filter_applied = False
    split_filter_complex = None

    if is_split_screen:
        if progress_callback:
            progress_callback({"percent": 35, "message": "Detecting dual speakers for split-screen layout..."})
        tracker = FaceTracker(smoothing_factor=0.2)
        split_crops = tracker.get_split_screen_crops(
            video_path=source_video_path,
            start_sec=start_time,
            duration_sec=duration
        )
        if split_crops:
            top_x, top_y, top_w, top_h = split_crops["top"]
            bot_x, bot_y, bot_w, bot_h = split_crops["bottom"]
            half_h = target_h // 2

            fc = (
                f"[0:v]crop={top_w}:{top_h}:{top_x}:{top_y},scale={target_w}:{half_h}:flags=lanczos[top];"
                f"[0:v]crop={bot_w}:{bot_h}:{bot_x}:{bot_y},scale={target_w}:{half_h}:flags=lanczos[bot];"
                f"[top][bot]vstack=inputs=2[vcomp]"
            )
            if subtitle_ass_path and subtitle_ass_path.exists():
                escaped_ass = escape_ffmpeg_path(subtitle_ass_path)
                fc += f";[vcomp]ass='{escaped_ass}'[vout]"
            else:
                fc += ";[vcomp]null[vout]"

            split_filter_complex = fc
            split_filter_applied = True

    # Standard video filters if not using split-screen
    filters = []
    if not split_filter_applied:
        if aspect_ratio == "16:9":
            # Direct scale without aspect alteration
            filters.append(f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2")
        else:
            # Smart Auto-Crop / Face Follow
            crop_ratio = target_w / target_h
            crop_h = orig_h
            crop_w = int(crop_h * crop_ratio)
            if crop_w > orig_w:
                crop_w = orig_w
                crop_h = int(crop_w / crop_ratio)

            crop_x = (orig_w - crop_w) // 2
            crop_y = 0

            tracker = FaceTracker(smoothing_factor=0.2)
            if ff_mode == "dynamic":
                if progress_callback:
                    progress_callback({"percent": 35, "message": "Applying dynamic speaker panning..."})
                dw, dh, x_expr = tracker.get_dynamic_pan_crop(
                    video_path=source_video_path,
                    start_sec=start_time,
                    duration_sec=duration,
                    target_aspect_ratio=crop_ratio
                )
                if dw > 0 and dh > 0:
                    filters.append(f"crop={dw}:{dh}:{x_expr}:0")
                else:
                    filters.append(f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}")
            elif ff_mode in ["single", "split"]:  # split falls back to single if dual faces not found
                if progress_callback:
                    progress_callback({"percent": 35, "message": "Applying dominant speaker centering..."})
                fx, fy, fw, fh = tracker.get_average_or_smooth_crop(
                    video_path=source_video_path,
                    start_sec=start_time,
                    duration_sec=duration,
                    target_aspect_ratio=crop_ratio
                )
                if fw > 0 and fh > 0:
                    crop_x = fx
                    crop_w = fw
                    crop_h = fh
                filters.append(f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}")
            else:
                # ff_mode == "none"
                filters.append(f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}")

            filters.append(f"scale={target_w}:{target_h}:flags=lanczos")

        # Add subtitle filter if generated
        if subtitle_ass_path and subtitle_ass_path.exists():
            escaped_ass = escape_ffmpeg_path(subtitle_ass_path)
            filters.append(f"ass='{escaped_ass}'")

    if progress_callback:
        progress_callback({"percent": 50, "message": "Rendering & encoding video clip with FFmpeg..."})

    # Assemble FFmpeg command
    if split_filter_applied:
        cmd = [
            ffmpeg_exe,
            "-y",
            "-ss", str(start_time),
            "-t", str(duration),
            "-i", str(source_video_path),
            "-filter_complex", split_filter_complex,
            "-map", "[vout]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "21",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-movflags", "+faststart",
            str(output_clip_path)
        ]
    else:
        filter_str = ",".join(filters)
        cmd = [
            ffmpeg_exe,
            "-y",
            "-ss", str(start_time),
            "-t", str(duration),
            "-i", str(source_video_path),
            "-vf", filter_str,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "21",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-movflags", "+faststart",
            str(output_clip_path)
        ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    _, stderr_data = process.communicate()

    if process.returncode != 0:
        print(f"FFmpeg error: {stderr_data}")
        # Try fallback without subtitles if ASS filter failed
        if subtitle_ass_path:
            clean_filters = [f for f in filters if not f.startswith("ass=")]
            clean_filter_str = ",".join(clean_filters) if clean_filters else f"scale={target_w}:{target_h}"
            fallback_cmd = [
                ffmpeg_exe, "-y",
                "-ss", str(start_time),
                "-t", str(duration),
                "-i", str(source_video_path),
                "-vf", clean_filter_str,
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_clip_path)
            ]
            fallback_proc = subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if fallback_proc.returncode != 0:
                raise RuntimeError(f"FFmpeg render failed: {stderr_data}")
        else:
            raise RuntimeError(f"FFmpeg render failed: {stderr_data}")

    # Generate standalone .srt for download if requested
    if subtitle_option in ["tiktok", "clean", "srt_only"] and transcript:
        srt_file = output_clip_path.with_suffix(".srt")
        generate_clip_srt(transcript, start_time, duration, srt_file)

    if progress_callback:
        progress_callback({"percent": 100, "message": "Clip finalized successfully!"})

    return output_clip_path
