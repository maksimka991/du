import json
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import List, Dict, Any, Optional

from backend.pack import Pack
from backend.storage import DATA_DIR, prepare_storage

DB_PATH = DATA_DIR / "du_learning.db"


def get_connection() -> sqlite3.Connection:
    prepare_storage()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    conn = get_connection()
    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS packs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_title TEXT NOT NULL,
                category TEXT NOT NULL,
                pack_type TEXT NOT NULL DEFAULT 'word_list',
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_id INTEGER,
                headword TEXT NOT NULL,
                translation TEXT NOT NULL,
                category TEXT NOT NULL,
                pack_type TEXT NOT NULL DEFAULT 'word_list',
                part_of_speech TEXT DEFAULT '',
                gender TEXT DEFAULT '',
                plural TEXT DEFAULT '',
                forms_summary TEXT DEFAULT '',
                mastery_level INTEGER DEFAULT 0,
                is_favorite INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE SET NULL,
                UNIQUE(headword, category)
            );

            CREATE TABLE IF NOT EXISTS sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL,
                level TEXT NOT NULL,
                de TEXT NOT NULL,
                uk TEXT NOT NULL,
                source TEXT DEFAULT 'Створено для навчання',
                grammar_tags_json TEXT DEFAULT '[]',
                complexity_notes_json TEXT DEFAULT '[]',
                tokens_json TEXT DEFAULT '[]',
                audio_de_normal TEXT DEFAULT '',
                audio_de_slow TEXT DEFAULT '',
                audio_uk TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS word_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                words_or_topic TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'word_list',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS review_state (
                card_id INTEGER PRIMARY KEY REFERENCES cards(id) ON DELETE CASCADE,
                due_at TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL,
                recall_streak INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS review_history (
                id INTEGER PRIMARY KEY,
                card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                rating TEXT NOT NULL CHECK (rating IN ('again', 'hard', 'good')),
                reviewed_at TEXT NOT NULL,
                due_at TEXT NOT NULL
            );
            """
        )
    conn.close()


CARD_FIELDS = ("translation", "pack_type", "part_of_speech", "gender", "plural", "forms_summary")
SENTENCE_FIELDS = (
    "level", "de", "uk", "source", "grammar_tags_json", "complexity_notes_json",
    "tokens_json", "sort_order",
)


def sentence_values(sentence, index):
    order = {"просте": 1, "середнє": 2, "складніше": 3}
    return (
        sentence.level, sentence.de, sentence.uk, sentence.source,
        json.dumps(sentence.grammar_tags, ensure_ascii=False),
        json.dumps(sentence.complexity_notes, ensure_ascii=False),
        json.dumps([token.model_dump(exclude_unset=True) for token in sentence.tokens], ensure_ascii=False),
        order.get(sentence.level, index + 1),
    )


def sentence_plan(old, new):
    remaining = list(old)
    matches = [None] * len(new)
    # Reserve exact text matches before considering edited sentences.
    for same in (
        lambda row, values: row["de"] == values[1] and row["uk"] == values[2],
        lambda row, values: row["de"] == values[1] or row["uk"] == values[2],
        lambda row, values: row["level"] == values[0],
    ):
        for index, values in enumerate(new):
            if matches[index] is None:
                match = next((row for row in remaining if same(row, values)), None)
                if match is not None:
                    remaining.remove(match)
                    matches[index] = match
    return list(zip(matches, new)), remaining


def same_sentence(row, values):
    return row is not None and all(
        json.loads(row[field]) == json.loads(value) if field.endswith("_json") else row[field] == value
        for field, value in zip(SENTENCE_FIELDS, values)
    )


def apply_sentences(conn, card_id, changes, removed):
    pending = []
    conn.executemany("DELETE FROM sentences WHERE id = ?", [(row["id"],) for row in removed])
    for old, values in changes:
        if old is None:
            cursor = conn.execute(
                f"INSERT INTO sentences (card_id, {', '.join(SENTENCE_FIELDS)}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (card_id, *values),
            )
            pending.append(cursor.lastrowid)
        elif not same_sentence(old, values):
            audio = (
                old["audio_de_normal"] if old["de"] == values[1] else "",
                old["audio_de_slow"] if old["de"] == values[1] else "",
                old["audio_uk"] if old["uk"] == values[2] else "",
            )
            assignments = ", ".join(f"{field} = ?" for field in SENTENCE_FIELDS)
            conn.execute(
                f"UPDATE sentences SET {assignments}, audio_de_normal = ?, audio_de_slow = ?, audio_uk = ? WHERE id = ?",
                (*values, *audio, old["id"]),
            )
            if not all(audio):
                pending.append(old["id"])
    return pending


def import_pack_data(pack: Pack, *, preview: bool = False) -> Dict[str, Any]:
    init_db()
    now = datetime.now().isoformat(timespec="seconds")
    counts = {"new": 0, "changed": 0, "unchanged": 0}
    result = {"counts": counts, "pack_id": None, "imported_cards": 0, "imported_sentences": 0,
              "card_ids": [], "audio_sentence_ids": []}
    with closing(get_connection()) as conn, conn:
        conn.execute("BEGIN" if preview else "BEGIN IMMEDIATE")
        for card in pack.cards:
            category = card.category or pack.category
            existing = conn.execute(
                "SELECT * FROM cards WHERE headword = ? AND category = ?",
                (card.headword, category),
            ).fetchone()
            values = (card.translation.strip(), card.pack_type or pack.pack_type,
                      card.part_of_speech, card.gender, card.plural, card.forms_summary)
            old = conn.execute(
                "SELECT * FROM sentences WHERE card_id = ? ORDER BY sort_order, id", (existing["id"],)
            ).fetchall() if existing else []
            changes, removed = sentence_plan(old, [
                sentence_values(sentence, index) for index, sentence in enumerate(card.sentences)
            ])
            identical = existing and tuple(existing[field] for field in CARD_FIELDS) == values
            identical = identical and not removed and all(same_sentence(row, new) for row, new in changes)
            if identical:
                counts["unchanged"] += 1
                continue
            counts["changed" if existing else "new"] += 1
            if preview:
                continue

            if result["pack_id"] is None:
                pack_row = conn.execute(
                    "SELECT id FROM packs WHERE pack_title = ? AND category = ? AND pack_type = ? ORDER BY id DESC LIMIT 1",
                    (pack.pack_title, pack.category, pack.pack_type),
                ).fetchone()
                if pack_row:
                    result["pack_id"] = pack_row["id"]
                    conn.execute("UPDATE packs SET description = ? WHERE id = ?", (pack.description, pack_row["id"]))
                else:
                    cursor = conn.execute(
                        "INSERT INTO packs (pack_title, category, pack_type, description, created_at) VALUES (?, ?, ?, ?, ?)",
                        (pack.pack_title, pack.category, pack.pack_type, pack.description, now),
                    )
                    result["pack_id"] = cursor.lastrowid
            pack_id = result["pack_id"]
            if existing:
                card_id = existing["id"]
                assignments = ", ".join(f"{field} = ?" for field in CARD_FIELDS)
                conn.execute(f"UPDATE cards SET pack_id = ?, {assignments} WHERE id = ?", (pack_id, *values, card_id))
            else:
                cursor = conn.execute(
                    f"INSERT INTO cards (pack_id, headword, category, {', '.join(CARD_FIELDS)}, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (pack_id, card.headword, category, *values, now),
                )
                card_id = cursor.lastrowid

            result["card_ids"].append(card_id)
            result["imported_cards"] += 1
            result["imported_sentences"] += len(changes)
            result["audio_sentence_ids"].extend(apply_sentences(conn, card_id, changes, removed))
    return result


def get_all_cards(
    pack_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    init_db()
    conn = get_connection()

    query = "SELECT * FROM cards WHERE 1=1"
    params: List[Any] = []

    if pack_type and pack_type != "all":
        query += " AND pack_type = ?"
        params.append(pack_type)

    if category and category != "all":
        query += " AND category = ?"
        params.append(category)

    if search:
        query += " AND (headword LIKE ? OR translation LIKE ? OR category LIKE ?)"
        like_q = f"%{search}%"
        params.extend([like_q, like_q, like_q])

    query += " ORDER BY id ASC"
    card_rows = conn.execute(query, params).fetchall()

    result = []
    for row in card_rows:
        card_dict = dict(row)
        sent_rows = conn.execute(
            "SELECT * FROM sentences WHERE card_id = ? ORDER BY sort_order ASC, id ASC",
            (row["id"],),
        ).fetchall()

        sentences = []
        for s in sent_rows:
            s_dict = dict(s)
            s_dict["grammar_tags"] = json.loads(s_dict.pop("grammar_tags_json", "[]"))
            s_dict["complexity_notes"] = json.loads(
                s_dict.pop("complexity_notes_json", "[]")
            )
            s_dict["tokens"] = json.loads(s_dict.pop("tokens_json", "[]"))
            sentences.append(s_dict)

        card_dict["sentences"] = sentences
        result.append(card_dict)

    conn.close()
    return result


def get_known_vocabulary(*, reviewed_only: bool = False) -> List[Dict[str, Any]]:
    init_db()
    conn = get_connection()
    reviewed = "WHERE id IN (SELECT card_id FROM review_state WHERE recall_streak >= 2)" if reviewed_only else ""
    rows = conn.execute(
        f"SELECT headword, translation, category, part_of_speech, mastery_level FROM cards {reviewed} ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_sentence_audio(
    sentence_id: int, audio_de_normal: str, audio_de_slow: str, audio_uk: str
) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            """
            UPDATE sentences
            SET audio_de_normal = ?, audio_de_slow = ?, audio_uk = ?
            WHERE id = ?
            """,
            (audio_de_normal, audio_de_slow, audio_uk, sentence_id),
        )
    conn.close()


def update_card_status(
    card_id: int,
    mastery_level: Optional[int] = None,
    is_favorite: Optional[int] = None,
) -> bool:
    conn = get_connection()
    with conn:
        if mastery_level is not None:
            conn.execute(
                "UPDATE cards SET mastery_level = ? WHERE id = ?",
                (mastery_level, card_id),
            )
        if is_favorite is not None:
            conn.execute(
                "UPDATE cards SET is_favorite = ? WHERE id = ?",
                (is_favorite, card_id),
            )
    conn.close()
    return True
