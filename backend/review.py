import json
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Literal

from backend.database import get_connection

Rating = Literal["again", "hard", "good"]
DAY = 24 * 60


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_review_queue() -> list[dict]:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """
            SELECT c.id AS card_id, r.due_at, s.*
            FROM cards AS c
            LEFT JOIN review_state AS r ON r.card_id = c.id
            JOIN sentences AS s ON s.id = (
                SELECT id FROM sentences WHERE card_id = c.id
                ORDER BY sort_order, id LIMIT 1
            )
            WHERE r.due_at IS NULL OR r.due_at <= ?
            ORDER BY r.due_at IS NULL, r.due_at, c.id
            LIMIT 50
            """,
            (utc_now().isoformat(),),
        ).fetchall()
    queue = []
    for row in rows:
        sentence = dict(row)
        card_id = sentence.pop("card_id")
        due_at = sentence.pop("due_at")
        for field in ("grammar_tags", "complexity_notes", "tokens"):
            sentence[field] = json.loads(sentence.pop(f"{field}_json"))
        queue.append({"card_id": card_id, "due_at": due_at, "sentence": sentence})
    return queue


def record_review(card_id: int, rating: Rating) -> dict:
    with closing(get_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        now = utc_now()
        if not conn.execute("SELECT 1 FROM sentences WHERE card_id = ? LIMIT 1", (card_id,)).fetchone():
            raise LookupError("Картка для повторення відсутня.")

        previous = conn.execute("SELECT * FROM review_state WHERE card_id = ?", (card_id,)).fetchone()
        if previous and previous["due_at"] > now.isoformat():
            raise ValueError("Цю картку вже оцінено. Оновіть чергу.")

        minutes = {"again": 10, "hard": DAY, "good": 3 * DAY}[rating]
        streak = 0
        if rating == "good":
            streak = 1
            if previous and previous["recall_streak"]:
                streak += previous["recall_streak"]
                minutes = min(previous["interval_minutes"] * 2, 30 * DAY)
        due_at = (now + timedelta(minutes=minutes)).isoformat()
        conn.execute(
            """
            INSERT INTO review_state (card_id, due_at, interval_minutes, recall_streak)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (card_id) DO UPDATE SET due_at = excluded.due_at,
                interval_minutes = excluded.interval_minutes, recall_streak = excluded.recall_streak
            """,
            (card_id, due_at, minutes, streak),
        )
        conn.execute(
            "INSERT INTO review_history (card_id, rating, reviewed_at, due_at) VALUES (?, ?, ?, ?)",
            (card_id, rating, now.isoformat(), due_at),
        )
    return {"card_id": card_id, "due_at": due_at, "interval_minutes": minutes, "recall_streak": streak}
