import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app import app
from backend.social.auth_manager import get_social_config, save_platform_config, get_public_account_status


class TestSocialPublishing(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_social_accounts_endpoint(self):
        res = self.client.get("/api/social/accounts")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        accounts = data.get("accounts", {})
        self.assertIn("youtube", accounts)
        self.assertIn("tiktok", accounts)
        self.assertIn("instagram", accounts)

    def test_save_and_retrieve_credentials(self):
        # Save sample dummy config
        save_res = self.client.post("/api/social/accounts", json={
            "platform": "youtube",
            "credentials": {"channel_name": "Test Studio", "access_token": "mock_token_123"}
        })
        self.assertEqual(save_res.status_code, 200)
        status = get_public_account_status()
        self.assertEqual(status["youtube"]["account_name"], "Test Studio")
        self.assertTrue(status["youtube"]["has_token"])

    def test_publish_validation(self):
        # Missing file should 404
        res = self.client.post("/api/social/publish", json={
            "file_path": "non_existent_file.mp4",
            "title": "Test Reel",
            "platforms": ["youtube"]
        })
        self.assertEqual(res.status_code, 404)

    def test_post_history_persistence(self):
        from backend.social.history_manager import add_post_history_entry, get_post_history, clear_all_history
        clear_all_history()

        # Add mock entry
        entry = add_post_history_entry(
            title="Viral Test Clip",
            file_path="output/test/clip_01.mp4",
            platforms=["youtube", "tiktok"],
            results={"youtube": {"success": True, "url": "https://youtube.com/shorts/test12345"}}
        )
        self.assertIsNotNone(entry.get("id"))

        # Verify via API endpoint
        res = self.client.get("/api/social/history")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        history = data.get("history", [])
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["title"], "Viral Test Clip")

        # Delete single item
        del_res = self.client.delete(f"/api/social/history/{entry['id']}")
        self.assertEqual(del_res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
