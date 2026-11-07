import json
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database, review
from backend.app import app
from test_import import LibraryTestCase


class ReviewTests(LibraryTestCase):
    def setUp(self):
        super().setUp()
        self.now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        clock = patch.object(review, "utc_now", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.card_id = self.queue()[0]["card_id"]

    def queue(self):
        response = self.client.get("/api/review/queue")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["queue"]

    def rate(self, rating):
        response = self.client.post(f"/api/review/{self.card_id}", json={"rating": rating})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def prompt(self):
        return self.client.post("/api/build-prompt", json={"user_input": "Test"}).json()

    def test_intervals_queue_and_duplicate_submission(self):
        for rating, minutes in [("again", 10), ("hard", 1440), ("good", 4320)]:
            result = self.rate(rating)
            self.assertEqual(result["interval_minutes"], minutes)
            self.assertEqual(result["due_at"], (self.now + timedelta(minutes=minutes)).isoformat())
            self.assertNotIn(self.card_id, [item["card_id"] for item in self.queue()])
            self.assertEqual(self.client.post(f"/api/review/{self.card_id}", json={"rating": rating}).status_code, 409)
            self.now += timedelta(minutes=minutes)
            self.assertEqual(self.queue()[0]["card_id"], self.card_id)
        with closing(database.get_connection()) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM review_history").fetchone()[0], 3)

    def test_recall_streak_and_prompt(self):
        self.assertIn("Базова лексика A1–A2", self.prompt()["prompt"])
        for days in (3, 6, 12, 24, 30, 30):
            result = self.rate("good")
            self.assertEqual(result["interval_minutes"], days * 1440)
            self.assertEqual(self.prompt()["known_words_count"], int(days >= 6))
            self.now += timedelta(days=days)
        result = self.rate("hard")
        self.assertEqual(result["recall_streak"], 0)
        self.assertEqual(self.prompt()["known_words_count"], 0)
        self.now += timedelta(days=1)
        self.assertEqual(self.rate("good")["interval_minutes"], 4320)

    def test_restart_and_reimport_preserve_review_history(self):
        result = self.rate("again")
        card = next(row for row in self.snapshot()[1] if row["id"] == self.card_id)
        pack = json.loads(self.raw)
        next(item for item in pack["cards"] if item["headword"] == card["headword"])["translation"] = "Оновлено"
        self.assertEqual(self.send(json.dumps(pack)).status_code, 200)
        with TestClient(app) as restarted:
            self.assertNotIn(self.card_id, [item["card_id"] for item in restarted.get("/api/review/queue").json()["queue"]])
            self.now += timedelta(minutes=10)
            self.assertEqual(restarted.get("/api/review/queue").json()["queue"][0]["due_at"], result["due_at"])
        with closing(database.get_connection()) as conn:
            self.assertEqual(conn.execute("SELECT rating FROM review_history WHERE card_id = ?", (self.card_id,)).fetchone()[0], "again")

    def test_invalid_rating_and_unknown_card(self):
        self.assertEqual(self.client.post(f"/api/review/{self.card_id}", json={"rating": "maybe"}).status_code, 422)
        self.assertEqual(self.client.post("/api/review/999999", json={"rating": "good"}).status_code, 404)
