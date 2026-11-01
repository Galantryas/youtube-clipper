import os
import sys
import uuid
import time
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .config_manager import load_autopilot_config
from .history_manager import (
    load_autopilot_history,
    get_processed_video_ids,
    add_autopilot_run_entry
)
from .trending_fetcher import fetch_multi_country_trending
from ..utils import sanitize_filename, get_output_dir, format_time, OUTPUT_DIR
from ..downloader import get_video_info, download_source_video
from ..subtitle_engine import fetch_youtube_transcript, detect_smart_clips
from ..clip_engine import process_single_clip
from ..social.publisher import publish_to_platforms


class AutopilotScheduler:
    def __init__(self):
        self.is_running = False
        self.is_executing = False
        self.last_run_date = None  # Format: YYYY-MM-DD
        self.current_job = None
        self._task = None

    def start(self):
        """Starts the background schedule monitor if not already running."""
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._schedule_loop())
        print("⚡ Auto-Pilot Daily Scheduler initialized and running in background.")

    def stop(self):
        """Stops the background schedule monitor."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _schedule_loop(self):
        """Monitors current time every 30 seconds and triggers auto-pilot at configured schedule_time."""
        while self.is_running:
            try:
                now = datetime.now()
                current_hhmm = now.strftime("%H:%M")
                current_date = now.strftime("%Y-%m-%d")

                config = load_autopilot_config()
                is_enabled = config.get("enabled", False)
                target_hhmm = config.get("schedule_time", "09:00")

                # Check trigger condition
                if is_enabled and current_hhmm == target_hhmm and self.last_run_date != current_date and not self.is_executing:
                    self.last_run_date = current_date
                    print(f"⏰ Auto-Pilot daily schedule triggered at {current_hhmm} for {current_date}")
                    asyncio.create_task(self.run_autopilot_pipeline(trigger_type="scheduled"))

            except asyncio.CancelledError:
                break
            except Exception as err:
                print(f"Warning in Auto-Pilot scheduler loop: {err}")

            await asyncio.sleep(30)

    def get_status(self) -> Dict[str, Any]:
        """Returns the current runtime state, next run time, and active job details."""
        config = load_autopilot_config()
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        
        # Determine next trigger date
        sched_time = config.get("schedule_time", "09:00")
        try:
            sched_hour, sched_minute = map(int, sched_time.split(":"))
            scheduled_today = now.replace(hour=sched_hour, minute=sched_minute, second=0, microsecond=0)
            if now >= scheduled_today or self.last_run_date == current_date:
                next_run_str = f"Tomorrow at {sched_time}"
            else:
                next_run_str = f"Today at {sched_time}"
        except Exception:
            next_run_str = f"Daily at {sched_time}"

        return {
            "scheduler_active": self.is_running,
            "enabled": config.get("enabled", False),
            "is_executing": self.is_executing,
            "schedule_time": sched_time,
            "next_scheduled_run": next_run_str if config.get("enabled") else "Disabled",
            "last_run_date": self.last_run_date,
            "current_job": self.current_job
        }

    async def run_autopilot_pipeline(self, trigger_type: str = "manual") -> Dict[str, Any]:
        """Executes the complete Auto-Pilot pipeline in the background."""
        if self.is_executing:
            return {"success": False, "message": "An Auto-Pilot job is already actively running."}

        self.is_executing = True
        run_id = f"run_{int(time.time())}_{str(uuid.uuid4())[:6]}"
        now = datetime.now()

        config = load_autopilot_config()
        countries = config.get("countries", ["US"])
        category = config.get("category", "all")
        max_videos = int(config.get("max_videos_per_run", 3))
        clip_prefs = config.get("clip_preferences", {})
        aspect_ratio = clip_prefs.get("aspect_ratio", "9:16")
        resolution = clip_prefs.get("resolution", "1080p")
        clip_count = int(clip_prefs.get("clip_count", 2))
        target_duration = float(clip_prefs.get("target_duration", 30.0))
        face_follow = clip_prefs.get("face_follow", "single")
        subtitle_option = clip_prefs.get("subtitle_option", "tiktok")

        upload_targets = config.get("upload_targets", {})
        privacy_status = config.get("privacy_status", "public")
        auto_publish_mode = config.get("auto_publish_mode", "auto_upload")
        title_template = config.get("title_template", "{clip_title} #shorts #trending")
        desc_template = config.get("description_template", "🔥 Trending viral moment from {video_title} by {channel}.\n\n#shorts #trending #{country_code} #viral")

        self.current_job = {
            "run_id": run_id,
            "trigger_type": trigger_type,
            "status": "running",
            "progress": 5,
            "message": f"Scraping top trending videos across {', '.join(countries)}...",
            "started_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "videos_found": 0,
            "videos_processed": [],
            "logs": []
        }

        def log_msg(msg: str):
            print(f"[Auto-Pilot] {msg}")
            if self.current_job:
                self.current_job["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
                self.current_job["message"] = msg

        loop = asyncio.get_event_loop()

        try:
            log_msg(f"Starting Auto-Pilot run ({trigger_type}) for countries: {countries}...")
            excluded_ids = get_processed_video_ids()
            
            # Step 1: Scrape Trending Videos
            trending_candidates = await loop.run_in_executor(
                None,
                fetch_multi_country_trending,
                countries,
                category,
                max_videos,
                excluded_ids
            )

            if not trending_candidates:
                log_msg("Notice: No new trending videos found (or all available candidates were already processed).")
                self.current_job["status"] = "completed"
                self.current_job["progress"] = 100
                report = self._finalize_run_entry(self.current_job, "completed")
                self.is_executing = False
                return report

            self.current_job["videos_found"] = len(trending_candidates)
            log_msg(f"Discovered {len(trending_candidates)} fresh trending videos to process.")

            # Step 2: Process each video sequentially
            total_vids = len(trending_candidates)
            for v_idx, v_meta in enumerate(trending_candidates):
                v_url = v_meta["url"]
                v_id = v_meta["video_id"]
                v_title = v_meta["title"]
                c_code = v_meta["country_code"]

                vid_prog_base = 10 + int((v_idx / total_vids) * 80)
                vid_prog_span = int(80 / total_vids)
                self.current_job["progress"] = vid_prog_base

                log_msg(f"Processing Video {v_idx + 1}/{total_vids}: '{v_title[:45]}...' ({v_id})")

                # 2a: Folder & Download
                video_folder = get_output_dir(v_title, v_id)
                source_download_path = video_folder / "source_video.mp4"

                # Check if already cached
                if not (source_download_path.exists() and source_download_path.stat().st_size > 50000):
                    log_msg(f"Downloading source stream for {v_id}...")
                    await loop.run_in_executor(
                        None,
                        download_source_video,
                        v_url,
                        source_download_path,
                        resolution
                    )

                # 2b: Transcript & NLP smart clips
                log_msg(f"Analyzing subtitles & sentence boundaries for {v_id}...")
                transcript = await loop.run_in_executor(None, fetch_youtube_transcript, v_id)
                
                # Fetch full info for exact duration
                info = await loop.run_in_executor(None, get_video_info, v_url)
                total_duration = info.get("duration", 0)

                clips_to_process = detect_smart_clips(
                    transcript=transcript,
                    total_duration=total_duration,
                    clip_count=clip_count,
                    target_duration=target_duration,
                    video_title=v_title
                )

                log_msg(f"Generated {len(clips_to_process)} sentence-aligned clip moments for '{v_title[:30]}'")

                # 2c: Slice, Face-track & Render clips
                generated_clips = []
                for c_idx, c_def in enumerate(clips_to_process):
                    safe_title = sanitize_filename(c_def["title"])
                    out_clip_name = f"clip_{c_idx+1:02d}_{aspect_ratio.replace(':', 'x')}_{safe_title}.mp4"
                    out_clip_path = video_folder / out_clip_name

                    await loop.run_in_executor(
                        None,
                        process_single_clip,
                        source_download_path,
                        out_clip_path,
                        c_def["start_time"],
                        c_def["duration"],
                        aspect_ratio,
                        resolution,
                        face_follow,
                        "crop",
                        subtitle_option,
                        transcript
                    )

                    srt_path = out_clip_path.with_suffix(".srt")
                    generated_clips.append({
                        "clip_index": c_idx + 1,
                        "title": c_def["title"],
                        "file_path": str(out_clip_path),
                        "relative_url": f"/output/{video_folder.name}/{out_clip_path.name}",
                        "duration": c_def["duration"],
                        "duration_formatted": format_time(c_def["duration"]),
                        "has_srt": srt_path.exists()
                    })

                # Save video project metadata
                meta_json_path = video_folder / "metadata.json"
                metadata_payload = {
                    "video_id": v_id,
                    "title": v_title,
                    "channel": v_meta["channel"],
                    "url": v_url,
                    "thumbnail": v_meta["thumbnail"],
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "aspect_ratio": aspect_ratio,
                    "resolution": resolution,
                    "face_follow": face_follow,
                    "subtitle_option": subtitle_option,
                    "folder_name": video_folder.name,
                    "folder_path": str(video_folder),
                    "clips": generated_clips
                }
                with open(meta_json_path, "w", encoding="utf-8") as f:
                    json.dump(metadata_payload, f, indent=2, ensure_ascii=False)

                # 2d: Auto-Publishing to Social Platforms
                upload_results = {}
                if auto_publish_mode == "auto_upload":
                    target_platforms = []
                    if upload_targets.get("youtube"):
                        target_platforms.append("youtube")
                    if upload_targets.get("tiktok"):
                        target_platforms.append("tiktok")
                    if upload_targets.get("instagram"):
                        target_platforms.append("instagram")

                    if target_platforms and generated_clips:
                        log_msg(f"Auto-publishing {len(generated_clips)} clips to {target_platforms}...")
                        for cl in generated_clips:
                            p_title = title_template.format(
                                video_title=v_title,
                                clip_title=cl["title"],
                                channel=v_meta["channel"],
                                country_code=c_code
                            )[:100]
                            p_desc = desc_template.format(
                                video_title=v_title,
                                clip_title=cl["title"],
                                channel=v_meta["channel"],
                                country_code=c_code
                            )

                            pub_res = await loop.run_in_executor(
                                None,
                                publish_to_platforms,
                                cl["file_path"],
                                p_title,
                                p_desc,
                                ["shorts", "trending", "viral", c_code.lower()],
                                target_platforms,
                                {
                                    "youtube_privacy": privacy_status,
                                    "tiktok_privacy": "PUBLIC_TO_EVERYONE" if privacy_status == "public" else "SELF_ONLY",
                                    "instagram_share_feed": True
                                }
                            )
                            upload_results[cl["title"]] = pub_res.get("results", {})

                # Record video processing summary
                self.current_job["videos_processed"].append({
                    "video_id": v_id,
                    "title": v_title,
                    "channel": v_meta["channel"],
                    "country_code": c_code,
                    "country_flag": v_meta.get("country_flag", "🌐"),
                    "thumbnail": v_meta["thumbnail"],
                    "clips_count": len(generated_clips),
                    "folder_name": video_folder.name,
                    "upload_results": upload_results
                })

            self.current_job["progress"] = 100
            self.current_job["status"] = "completed"
            log_msg(f"🎉 Auto-Pilot run finished! Successfully processed {len(self.current_job['videos_processed'])} trending videos.")

            report = self._finalize_run_entry(self.current_job, "completed")
            self.is_executing = False
            return report

        except Exception as err:
            log_msg(f"❌ Auto-Pilot run encountered an error: {err}")
            self.current_job["status"] = "failed"
            self.current_job["error"] = str(err)
            report = self._finalize_run_entry(self.current_job, "failed")
            self.is_executing = False
            return report

    def _finalize_run_entry(self, job_data: Dict[str, Any], final_status: str) -> Dict[str, Any]:
        """Saves run details into persistent history."""
        run_entry = {
            "run_id": job_data["run_id"],
            "trigger_type": job_data["trigger_type"],
            "status": final_status,
            "started_at": job_data["started_at"],
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "videos_found": job_data.get("videos_found", 0),
            "videos_processed": job_data.get("videos_processed", []),
            "logs": job_data.get("logs", [])
        }
        add_autopilot_run_entry(run_entry)
        return run_entry


# Global singleton instance
autopilot_engine = AutopilotScheduler()
