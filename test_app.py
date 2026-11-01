import sys
import unittest
from pathlib import Path

from backend.utils import sanitize_filename, format_time, get_ffmpeg_path, get_output_dir
from backend.clip_engine import get_target_resolution
from backend.subtitle_engine import format_srt_time, format_ass_time, generate_styled_ass
from backend.downloader import extract_video_id


class TestYoutubeClipper(unittest.TestCase):
    def test_utils(self):
        self.assertEqual(sanitize_filename("Hello / World : Test?"), "Hello_World_Test")
        self.assertEqual(format_time(65), "01:05")
        self.assertEqual(format_time(3665), "01:01:05")
        ffmpeg_path = get_ffmpeg_path()
        self.assertTrue(len(ffmpeg_path) > 0)
        print(f"Verified FFmpeg at: {ffmpeg_path}")

    def test_video_id_extraction(self):
        self.assertEqual(extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(extract_video_id("https://youtu.be/dQw4w9WgXcQ?t=10"), "dQw4w9WgXcQ")
        self.assertEqual(extract_video_id("https://youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(extract_video_id("dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_resolutions(self):
        w, h = get_target_resolution("9:16", "1080p")
        self.assertEqual((w, h), (1080, 1920))

        w, h = get_target_resolution("1:1", "1080p")
        self.assertEqual((w, h), (1080, 1080))

        w, h = get_target_resolution("16:9", "1080p")
        self.assertEqual((w, h), (1920, 1080))

        w, h = get_target_resolution("9:16", "720p")
        self.assertEqual((w, h), (720, 1280))

    def test_subtitles_formatting(self):
        self.assertEqual(format_srt_time(61.5), "00:01:01,500")
        self.assertEqual(format_ass_time(61.5), "0:01:01.50")

    def test_smart_clip_nlp_analysis(self):
        from backend.subtitle_engine import build_sentence_blocks, clean_hook_title, detect_smart_clips
        sample_transcript = [
            {"text": "Hey guys welcome back.", "start": 0.0, "duration": 2.0},
            {"text": "Today I want to share", "start": 2.2, "duration": 1.5},
            {"text": "the biggest mistake", "start": 3.8, "duration": 1.2},
            {"text": "that people make every single day.", "start": 5.1, "duration": 2.4},
            {"text": "If you want to grow,", "start": 8.0, "duration": 1.8},
            {"text": "you must avoid this completely.", "start": 10.0, "duration": 2.5},
            {"text": "First, stop doing random tasks.", "start": 13.0, "duration": 2.5},
            {"text": "Focus on high leverage work.", "start": 16.0, "duration": 2.5},
            {"text": "Second, build your personal brand.", "start": 20.0, "duration": 3.0},
            {"text": "Why is this so important?", "start": 23.5, "duration": 2.0},
            {"text": "Because it gives you leverage forever.", "start": 26.0, "duration": 3.0},
            {"text": "Thanks for watching, see you next time!", "start": 35.0, "duration": 3.0}
        ]

        blocks = build_sentence_blocks(sample_transcript)
        self.assertTrue(len(blocks) >= 3)
        self.assertTrue(any("mistake" in b["text"].lower() for b in blocks))

        clips = detect_smart_clips(sample_transcript, total_duration=40.0, clip_count=2, target_duration=20.0)
        self.assertTrue(len(clips) >= 1)
        self.assertTrue("start_time" in clips[0])
        self.assertTrue("duration" in clips[0])
        self.assertTrue("title" in clips[0])
        print(f"Detected Smart Clips: {clips}")

    def test_face_tracker_methods(self):
        from backend.face_tracker import FaceTracker
        tracker = FaceTracker()
        self.assertIsNotNone(tracker)
        # Test empty video path fallback handling
        crop = tracker.get_average_or_smooth_crop("nonexistent.mp4", 0, 10)
        self.assertEqual(crop, (0, 0, 0, 0))


if __name__ == "__main__":
    unittest.main()
