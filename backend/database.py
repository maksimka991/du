import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "du_learning.db"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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
            """
        )
    conn.close()


def import_pack_data(pack_data: Dict[str, Any]) -> Dict[str, Any]:
    init_db()
    conn = get_connection()
    now = datetime.now().isoformat(timespec="seconds")

    pack_title = pack_data.get("pack_title", "Навчальний набір")
    category = pack_data.get("category", "Загальне")
    pack_type = pack_data.get("pack_type", "word_list")
    description = pack_data.get("description", "")

    imported_cards = 0
    imported_sentences = 0
    card_ids = []

    with conn:
        cur = conn.execute(
            """
            INSERT INTO packs (pack_title, category, pack_type, description, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (pack_title, category, pack_type, description, now),
        )
        pack_id = cur.lastrowid

        for card in pack_data.get("cards", []):
            headword = card["headword"].strip()
            card_category = card.get("category") or category
            card_pack_type = card.get("pack_type") or pack_type
            translation = card.get("translation", "").strip()
            pos = card.get("part_of_speech", "")
            gender = card.get("gender", "")
            plural = card.get("plural", "")
            forms_summary = card.get("forms_summary", "")

            existing = conn.execute(
                "SELECT id FROM cards WHERE headword = ? AND category = ?",
                (headword, card_category),
            ).fetchone()

            if existing:
                card_id = existing["id"]
                conn.execute(
                    """
                    UPDATE cards
                    SET pack_id = ?, translation = ?, pack_type = ?, part_of_speech = ?,
                        gender = ?, plural = ?, forms_summary = ?
                    WHERE id = ?
                    """,
                    (
                        pack_id,
                        translation,
                        card_pack_type,
                        pos,
                        gender,
                        plural,
                        forms_summary,
                        card_id,
                    ),
                )
                conn.execute("DELETE FROM sentences WHERE card_id = ?", (card_id,))
            else:
                c_cur = conn.execute(
                    """
                    INSERT INTO cards (
                        pack_id, headword, translation, category, pack_type,
                        part_of_speech, gender, plural, forms_summary, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pack_id,
                        headword,
                        translation,
                        card_category,
                        card_pack_type,
                        pos,
                        gender,
                        plural,
                        forms_summary,
                        now,
                    ),
                )
                card_id = c_cur.lastrowid

            imported_cards += 1
            card_ids.append(card_id)

            level_order = {"просте": 1, "середнє": 2, "складніше": 3}
            for idx, sent in enumerate(card.get("sentences", [])):
                lvl = sent.get("level", "просте")
                s_order = level_order.get(lvl, idx + 1)
                conn.execute(
                    """
                    INSERT INTO sentences (
                        card_id, level, de, uk, source,
                        grammar_tags_json, complexity_notes_json, tokens_json, sort_order
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        card_id,
                        lvl,
                        sent["de"].strip(),
                        sent["uk"].strip(),
                        sent.get("source", "Створено для навчання"),
                        json.dumps(sent.get("grammar_tags", []), ensure_ascii=False),
                        json.dumps(sent.get("complexity_notes", []), ensure_ascii=False),
                        json.dumps(sent.get("tokens", []), ensure_ascii=False),
                        s_order,
                    ),
                )
                imported_sentences += 1

    conn.close()
    return {
        "pack_id": pack_id,
        "imported_cards": imported_cards,
        "imported_sentences": imported_sentences,
        "card_ids": card_ids,
    }


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


def get_known_vocabulary() -> List[Dict[str, str]]:
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT headword, translation, category, part_of_speech, mastery_level FROM cards ORDER BY id ASC"
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
