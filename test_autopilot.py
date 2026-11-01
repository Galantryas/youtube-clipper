import unittest
from backend.autopilot.config_manager import load_autopilot_config, save_autopilot_config, DEFAULT_CONFIG
from backend.autopilot.history_manager import (
    load_autopilot_history,
    add_autopilot_run_entry,
    get_processed_video_ids,
    clear_autopilot_history
)
from backend.autopilot.trending_fetcher import COUNTRY_MAP, COUNTRY_EMOJIS, fetch_country_trending
from backend.autopilot.scheduler import autopilot_engine
from fastapi.testclient import TestClient
from backend.app import app


class TestAutopilotEngine(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_country_mappings(self):
        self.assertIn("US", COUNTRY_MAP)
        self.assertIn("ID", COUNTRY_MAP)
        self.assertIn("GB", COUNTRY_MAP)
        self.assertEqual(COUNTRY_EMOJIS.get("ID"), "🇮🇩")
        self.assertEqual(COUNTRY_EMOJIS.get("US"), "🇺🇸")

    def test_config_manager(self):
        cfg = load_autopilot_config()
        self.assertIn("enabled", cfg)
        self.assertIn("schedule_time", cfg)
        self.assertIn("countries", cfg)
        self.assertIn("clip_preferences", cfg)
        self.assertIn("upload_targets", cfg)

        # Test updating config
        cfg["schedule_time"] = "10:30"
        cfg["countries"] = ["US", "ID", "GB"]
        res = save_autopilot_config(cfg)
        self.assertTrue(res)

        reloaded = load_autopilot_config()
        self.assertEqual(reloaded["schedule_time"], "10:30")
        self.assertEqual(reloaded["countries"], ["US", "ID", "GB"])

    def test_history_deduplication(self):
        dummy_entry = {
            "run_id": "test_run_123",
            "trigger_type": "manual",
            "status": "completed",
            "started_at": "2026-08-30 20:00:00",
            "finished_at": "2026-08-30 20:05:00",
            "videos_found": 1,
            "videos_processed": [
                {
                    "video_id": "dQw4w9WgXcQ",
                    "title": "Never Gonna Give You Up",
                    "channel": "Rick Astley",
                    "country_code": "US",
                    "clips_count": 2,
                    "folder_name": "Never_Gonna_Give_You_Up_dQw4w9WgXcQ",
                    "upload_results": {}
                }
            ],
            "logs": ["Test log"]
        }
        add_autopilot_run_entry(dummy_entry)
        seen = get_processed_video_ids()
        self.assertIn("dQw4w9WgXcQ", seen)

    def test_scheduler_status(self):
        status = autopilot_engine.get_status()
        self.assertIn("enabled", status)
        self.assertIn("schedule_time", status)
        self.assertIn("next_scheduled_run", status)

    def test_api_endpoints(self):
        # 1. GET /api/autopilot/config
        r = self.client.get("/api/autopilot/config")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data.get("success"))
        self.assertIn("country_options", data)

        # 2. POST /api/autopilot/config
        payload = data["config"]
        payload["enabled"] = False
        payload["schedule_time"] = "09:00"
        payload["countries"] = ["US", "ID"]
        r2 = self.client.post("/api/autopilot/config", json=payload)
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json().get("success"))

        # 3. GET /api/autopilot/status
        r3 = self.client.get("/api/autopilot/status")
        self.assertEqual(r3.status_code, 200)
        self.assertTrue(r3.json().get("success"))

        # 4. GET /api/autopilot/history
        r4 = self.client.get("/api/autopilot/history")
        self.assertEqual(r4.status_code, 200)
        self.assertTrue(r4.json().get("success"))


if __name__ == "__main__":
    unittest.main()
