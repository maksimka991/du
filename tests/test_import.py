import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import database, storage, tts_service
from backend.app import app

PACK = storage.DEMO_DIR / "packs" / "starter_pack.json"


class ImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name) / "library"
        self.raw = PACK.read_text(encoding="utf-8")
        for module, name, value in [
            (storage, "DATA_DIR", directory),
            (database, "DB_PATH", directory / "du_learning.db"),
            (tts_service, "AUDIO_DIR", directory / "audio"),
        ]:
            override = patch.object(module, name, value)
            override.start()
            self.addCleanup(override.stop)
        database.init_db()
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def snapshot(self):
        with closing(database.get_connection()) as conn:
            return tuple(conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
                         for table in ("packs", "cards", "sentences"))

    def send(self, raw, **options):
        return self.client.post("/api/import-pack", json={"json_text": raw, "generate_tts": False, **options})

    def test_invalid_packages_leave_database_unchanged(self):
        original = self.snapshot()
        for raw in ("null", '{"cards":[{}]}', '{"cards":[{"headword":"Test","sentences":[]}]}'):
            with self.subTest(raw=raw):
                self.assertEqual(self.send(raw).status_code, 400)
        response = self.send('{"cards":[{"headword":"Test","sentences":[{"uk":"Test"}]}]}')
        self.assertIn("cards[0].sentences[0].de", response.json()["detail"])
        self.assertEqual(original, self.snapshot())

    def test_identical_import_preserves_library(self):
        original = self.snapshot()
        self.assertEqual((len(original[0]), len(original[2])), (2, 45))
        for row in original[2]:
            for field in ("audio_de_normal", "audio_de_slow", "audio_uk"):
                self.assertTrue(row[field])
                self.assertTrue((tts_service.AUDIO_DIR / Path(row[field]).name).is_file())
        for path in (PACK, PACK.with_name("pack_last_10.json")):
            raw = path.read_text(encoding="utf-8")
            response = self.send("```json\n" + raw + "\n```")
            self.assertEqual(response.status_code, 200, response.text)
            counts = response.json()["import"]["counts"]
            self.assertEqual(counts, {"new": 0, "changed": 0, "unchanged": len(json.loads(raw)["cards"])})
        self.assertEqual(original, self.snapshot())

    def test_preview_then_translation_edit_preserves_german_tracks(self):
        original = self.snapshot()
        pack = json.loads(self.raw)
        sentence = pack["cards"][0]["sentences"][0]
        before = next(row for row in original[2] if row["de"] == sentence["de"] and row["uk"] == sentence["uk"])
        sentence["uk"] = "Новий переклад."
        raw = json.dumps(pack)
        self.assertEqual(self.send(raw, preview=True).json()["import"]["counts"]["changed"], 1)
        self.assertEqual(original, self.snapshot())
        result = self.send(raw).json()["import"]
        self.assertEqual(result["audio_sentence_ids"], [before["id"]])
        updated = next(row for row in self.snapshot()[2] if row["id"] == before["id"])
        self.assertEqual(updated["audio_de_normal"], before["audio_de_normal"])
        self.assertEqual(updated["audio_de_slow"], before["audio_de_slow"])
        self.assertEqual(updated["audio_uk"], "")

    def test_tts_failure_is_retryable(self):
        class BrokenAudio:
            async def save(self, path):
                Path(path).write_bytes(b"x" * 300)
                raise OSError("network unavailable")

        class GoodAudio:
            async def save(self, path):
                Path(path).write_bytes(b"x" * 300)

        raw = json.dumps({"cards": [{"headword": "Testwort", "sentences": [{"de": "Ein Testwort.", "uk": "Тест."}]}]})
        with patch.object(tts_service.edge_tts, "Communicate", return_value=BrokenAudio()):
            response = self.send(raw, generate_tts=True)
        self.assertEqual(response.status_code, 200, response.text)
        stats = response.json()["tts"]
        self.assertEqual(stats["failed"], 1)
        self.assertFalse(list(tts_service.AUDIO_DIR.glob("*.part")))
        self.assertEqual(self.client.get("/api/cards?search=Testwort").json()["cards"][0]["headword"], "Testwort")
        with patch.object(tts_service.edge_tts, "Communicate", return_value=GoodAudio()):
            stats = self.client.post("/api/generate-audio").json()["stats"]
        self.assertEqual((stats["generated"], stats["failed"]), (1, 0))

    def test_existing_runtime_library_is_not_overwritten(self):
        with closing(database.get_connection()) as conn, conn:
            conn.execute("UPDATE cards SET mastery_level = 2")
        storage.prepare_storage()
        self.assertTrue(all(row["mastery_level"] == 2 for row in self.snapshot()[1]))
