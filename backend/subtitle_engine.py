import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound


def fetch_youtube_transcript(video_id: str, preferred_languages: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Fetches transcript segments with start and duration from YouTube transcript API.
    Returns: [{'text': '...', 'start': 12.3, 'duration': 4.5}, ...]
    """
    if preferred_languages is None:
        preferred_languages = ["en", "en-US", "id", "es", "ja", "ko", "de", "fr", "pt", "ru", "hi"]

    try:
        api = YouTubeTranscriptApi()
        # Direct fetch attempt
        try:
            raw_res = api.fetch(video_id, languages=preferred_languages)
            # Support both object-based transcript and dictionary items
            results = []
            for item in raw_res:
                if isinstance(item, dict):
                    results.append({
                        "text": item.get("text", ""),
                        "start": float(item.get("start", 0)),
                        "duration": float(item.get("duration", 0))
                    })
                elif hasattr(item, "text"):
                    results.append({
                        "text": getattr(item, "text", ""),
                        "start": float(getattr(item, "start", 0)),
                        "duration": float(getattr(item, "duration", 0))
                    })
            if results:
                return results
        except Exception:
            pass

        # Try list transcripts
        if hasattr(api, "list"):
            transcript_list = api.list(video_id)
            for t in transcript_list:
                fetched = t.fetch()
                return [
                    {
                        "text": item.get("text", "") if isinstance(item, dict) else getattr(item, "text", ""),
                        "start": float(item.get("start", 0) if isinstance(item, dict) else getattr(item, "start", 0)),
                        "duration": float(item.get("duration", 0) if isinstance(item, dict) else getattr(item, "duration", 0))
                    }
                    for item in fetched
                ]
    except Exception as e:
        print(f"Notice: Transcript fetch unavailable for {video_id}: {e}")

    return []


def format_srt_time(seconds: float) -> str:
    """Formats seconds into SRT time format: 00:01:23,456"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def format_ass_time(seconds: float) -> str:
    """Formats seconds into ASS time format: 0:01:23.45"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int((seconds - int(seconds)) * 100)
    return f"{hrs}:{mins:02d}:{secs:02d}.{centis:02d}"


def generate_clip_srt(
    transcript: List[Dict[str, Any]],
    clip_start: float,
    clip_duration: float,
    output_path: Path
) -> Optional[Path]:
    """Generates standard .srt subtitle file adjusted for clip start offset."""
    clip_end = clip_start + clip_duration
    relevant_lines = []

    for item in transcript:
        item_start = item.get("start", 0)
        item_dur = item.get("duration", 0)
        item_end = item_start + item_dur

        if item_end >= clip_start and item_start <= clip_end:
            rel_start = max(0.0, item_start - clip_start)
            rel_end = min(clip_duration, item_end - clip_start)
            text = item.get("text", "").strip().replace("\n", " ")
            if text and rel_end > rel_start:
                relevant_lines.append((rel_start, rel_end, text))

    if not relevant_lines:
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for idx, (s, e, text) in enumerate(relevant_lines, 1):
            f.write(f"{idx}\n")
            f.write(f"{format_srt_time(s)} --> {format_srt_time(e)}\n")
            f.write(f"{text}\n\n")

    return output_path


def generate_styled_ass(
    transcript: List[Dict[str, Any]],
    clip_start: float,
    clip_duration: float,
    output_path: Path,
    style_type: str = "tiktok",
    is_vertical: bool = True
) -> Optional[Path]:
    """
    Generates an Advanced SubStation Alpha (.ass) subtitle file with high-contrast social styling.
    """
    clip_end = clip_start + clip_duration
    raw_segments = []

    for item in transcript:
        item_start = item.get("start", 0)
        item_dur = item.get("duration", 0)
        item_end = item_start + item_dur

        if item_end >= clip_start and item_start <= clip_end:
            rel_start = max(0.0, item_start - clip_start)
            rel_end = min(clip_duration, item_end - clip_start)
            text = item.get("text", "").strip().replace("\n", " ")
            if text and rel_end > rel_start:
                words = text.split()
                if len(words) > 6:
                    chunk_size = 4
                    total_chunks = (len(words) + chunk_size - 1) // chunk_size
                    chunk_duration = (rel_end - rel_start) / total_chunks
                    for i in range(total_chunks):
                        c_start = rel_start + (i * chunk_duration)
                        c_end = min(rel_end, c_start + chunk_duration)
                        c_text = " ".join(words[i * chunk_size : (i + 1) * chunk_size])
                        raw_segments.append((c_start, c_end, c_text))
                else:
                    raw_segments.append((rel_start, rel_end, text))

    if not raw_segments:
        return None

    font_size = 26 if is_vertical else 20
    margin_v = 130 if is_vertical else 60

    primary_color = "&H0000FFFF" if style_type == "tiktok" else "&H00FFFFFF"
    outline_color = "&H00000000"
    back_color = "&H80000000"

    ass_header = f"""[Script Info]
Title: Youtube Clipper Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,{font_size * 2},{primary_color},&H000000FF,{outline_color},{back_color},-1,0,0,0,100,100,0,0,1,6,2,2,40,40,{margin_v * 2},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_header)
        for s, e, text in raw_segments:
            clean_txt = text.upper() if style_type == "tiktok" else text
            f.write(f"Dialogue: 0,{format_ass_time(s)},{format_ass_time(e)},Default,,0,0,0,,{clean_txt}\n")

    return output_path


HOOK_KEYWORDS = {
    # Curiosity & Secrets
    "secret", "secret is", "the truth", "nobody tells you", "real reason", "hidden",
    "mistake", "biggest mistake", "warning", "never do this", "stop doing",
    # Question Hooks
    "how to", "why you", "why is", "what happens", "what if", "did you know",
    "have you ever", "how do you", "can you actually",
    # High Emotion & Virality
    "insane", "crazy", "unbelievable", "shocking", "mind blowing", "game changer",
    "guaranteed", "must know", "best way", "worst way", "number one",
    # Direct Callouts / Actions
    "look at this", "watch this", "check this out", "listen to this", "pay attention",
    "remember this", "key takeaway", "here is the thing", "the point is", "solution",
    "result", "tip", "hack", "strategy", "method", "step 1", "first step", "formula", "rule"
}


def build_sentence_blocks(transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Aggregates fragmented transcript segments into coherent sentence/thought blocks
    with precise start and end timestamps.
    """
    if not transcript:
        return []

    blocks = []
    curr_words = []
    curr_start = None
    curr_end = 0.0

    for i, seg in enumerate(transcript):
        raw_text = seg.get("text", "").strip().replace("\n", " ")
        if not raw_text:
            continue

        seg_start = float(seg.get("start", 0.0))
        seg_dur = float(seg.get("duration", 0.0))
        seg_end = seg_start + seg_dur

        if curr_start is None:
            curr_start = seg_start

        # Check pause between previous segment and current segment
        pause_gap = seg_start - curr_end if curr_end > 0 else 0

        curr_words.append(raw_text)
        curr_end = seg_end

        combined_text = " ".join(curr_words)
        has_terminal_punct = any(combined_text.rstrip().endswith(p) for p in [".", "!", "?"])
        long_pause = pause_gap > 0.8
        enough_words = len(combined_text.split()) >= 5

        # If sentence finished, or long pause with enough words, or segment is getting long
        if (has_terminal_punct and enough_words) or (long_pause and enough_words) or (curr_end - curr_start >= 12.0):
            clean_sentence = combined_text.strip()
            blocks.append({
                "start": round(curr_start, 2),
                "end": round(curr_end, 2),
                "duration": round(curr_end - curr_start, 2),
                "text": clean_sentence,
                "word_count": len(clean_sentence.split()),
            })
            curr_words = []
            curr_start = None

    if curr_words and curr_start is not None:
        clean_sentence = " ".join(curr_words).strip()
        blocks.append({
            "start": round(curr_start, 2),
            "end": round(curr_end, 2),
            "duration": round(curr_end - curr_start, 2),
            "text": clean_sentence,
            "word_count": len(clean_sentence.split()),
        })

    return blocks


def clean_hook_title(text: str) -> str:
    """Derives a catchy, clean title from a sentence for TikTok/Shorts display."""
    # Remove intro filler words
    t = re.sub(r"^(so|and|like|but|um|uh|well|you know|i mean|basically|actually),?\s*", "", text, flags=re.IGNORECASE).strip()
    # Capitalize first letter
    if t:
        t = t[0].upper() + t[1:]
    # Limit length and strip trailing punctuation for clean title
    t = t.rstrip(".,;:-!?")
    words = t.split()
    if len(words) > 8:
        t = " ".join(words[:8])
    return t or "Viral Moment"


def detect_smart_clips(
    transcript: List[Dict[str, Any]],
    total_duration: float,
    clip_count: int = 3,
    target_duration: float = 30.0,
    video_title: str = ""
) -> List[Dict[str, Any]]:
    """
    Analyzes transcript semantics, sentence boundaries, and hook density
    to detect the most engaging, non-overlapping clips aligned to complete dialogue thoughts.
    """
    sentence_blocks = build_sentence_blocks(transcript)

    if sentence_blocks and len(sentence_blocks) >= 2:
        min_dur = max(15.0, target_duration - 12.0)
        max_dur = min(total_duration, target_duration + 12.0)

        candidate_windows = []

        # Slide start block from index 0 to len(sentence_blocks)
        for start_idx in range(len(sentence_blocks)):
            w_start = sentence_blocks[start_idx]["start"]
            first_block_text = sentence_blocks[start_idx]["text"].lower()

            # Evaluate potential end blocks
            for end_idx in range(start_idx, len(sentence_blocks)):
                w_end = sentence_blocks[end_idx]["end"]
                w_dur = w_end - w_start

                if w_dur < min_dur:
                    continue
                if w_dur > max_dur:
                    break  # Exceeded max duration, move to next start block

                # Combine text across the window
                window_blocks = sentence_blocks[start_idx : end_idx + 1]
                full_text = " ".join(b["text"] for b in window_blocks).lower()
                total_words = sum(b["word_count"] for b in window_blocks)

                # 1. Opener Hook Score (0 - 50 points)
                hook_score = 0.0
                for kw in HOOK_KEYWORDS:
                    if kw in first_block_text:
                        hook_score += 15.0
                    elif kw in full_text:
                        hook_score += 4.0
                if any(first_block_text.startswith(q) for q in ["why", "how", "what", "can you", "did you", "is it"]):
                    hook_score += 15.0
                if "?" in first_block_text:
                    hook_score += 10.0
                if "!" in first_block_text:
                    hook_score += 8.0

                hook_score = min(50.0, hook_score)

                # 2. Speech Flow & Density Score (0 - 30 points)
                words_per_sec = total_words / max(1.0, w_dur)
                if 2.2 <= words_per_sec <= 4.0:
                    density_score = 30.0
                elif 1.5 <= words_per_sec < 2.2:
                    density_score = 20.0
                else:
                    density_score = 10.0

                # 3. Target Duration Proximity Score (0 - 20 points)
                dur_diff = abs(w_dur - target_duration)
                dur_score = max(0.0, 20.0 - (dur_diff * 1.5))

                # 4. Sentence Boundary / Narrative Completeness (0 - 10 points)
                last_block_text = sentence_blocks[end_idx]["text"]
                closing_score = 10.0 if any(last_block_text.rstrip().endswith(p) for p in [".", "!", "?"]) else 5.0

                total_score = hook_score + density_score + dur_score + closing_score

                title_preview = clean_hook_title(sentence_blocks[start_idx]["text"])

                candidate_windows.append({
                    "start_time": round(w_start, 2),
                    "end_time": round(w_end, 2),
                    "duration": round(w_dur, 2),
                    "score": round(total_score, 1),
                    "title": title_preview,
                    "sample_text": sentence_blocks[start_idx]["text"][:60]
                })

        # Sort all candidate windows by score descending
        candidate_windows.sort(key=lambda x: x["score"], reverse=True)

        # Select top non-overlapping clips distributed across the video
        selected_clips = []
        min_gap_between_clips = 5.0  # seconds

        for cand in candidate_windows:
            if len(selected_clips) >= clip_count:
                break
            c_start = cand["start_time"]
            c_end = cand["end_time"]

            overlaps = False
            for sel in selected_clips:
                s_start = sel["start_time"] - min_gap_between_clips
                s_end = sel["end_time"] + min_gap_between_clips
                if not (c_end <= s_start or c_start >= s_end):
                    overlaps = True
                    break

            if not overlaps:
                selected_clips.append(cand)

        # Sort chronologically by start_time for a nice presentation
        selected_clips.sort(key=lambda x: x["start_time"])

        # If we need more clips and couldn't find enough non-overlapping high scorers
        if len(selected_clips) < clip_count and total_duration > target_duration:
            step = total_duration / (clip_count + 1)
            for i in range(clip_count):
                if len(selected_clips) >= clip_count:
                    break
                ideal_start = (i + 1) * step
                closest_block = min(sentence_blocks, key=lambda b: abs(b["start"] - ideal_start))
                b_start = closest_block["start"]
                b_dur = min(target_duration, total_duration - b_start)
                if b_dur >= 10.0:
                    overlaps = any(not ((b_start + b_dur) <= s["start_time"] or b_start >= s["end_time"]) for s in selected_clips)
                    if not overlaps:
                        selected_clips.append({
                            "start_time": round(b_start, 2),
                            "end_time": round(b_start + b_dur, 2),
                            "duration": round(b_dur, 2),
                            "score": 50.0,
                            "title": clean_hook_title(closest_block["text"])
                        })
                        selected_clips.sort(key=lambda x: x["start_time"])

        # Format final output with clean titles and indices
        formatted_clips = []
        for idx, c in enumerate(selected_clips):
            formatted_clips.append({
                "clip_index": idx + 1,
                "title": f"Clip {idx+1}: {c['title']}",
                "start_time": c["start_time"],
                "duration": c["duration"],
                "end_time": c["end_time"],
                "hook_score": c.get("score", 70.0)
            })

        if formatted_clips:
            return formatted_clips

    # Fallback for videos without transcripts
    segment_len = min(target_duration, total_duration)
    if total_duration <= segment_len:
        return [{
            "clip_index": 1,
            "title": f"Highlight: {video_title[:40] or 'Full Video'}",
            "start_time": 0.0,
            "duration": round(total_duration, 2),
            "end_time": round(total_duration, 2)
        }]

    fallback_clips = []
    spacing = (total_duration - segment_len) / max(1, clip_count)
    for i in range(clip_count):
        st = round(i * spacing, 2)
        fallback_clips.append({
            "clip_index": i + 1,
            "title": f"Moment {i+1} ({format_srt_time(st).split(',')[0]} - {format_srt_time(st + segment_len).split(',')[0]})",
            "start_time": st,
            "duration": round(segment_len, 2),
            "end_time": round(st + segment_len, 2)
        })
    return fallback_clips
