import hashlib
from contextlib import closing
from uuid import uuid4
import edge_tts

from backend.database import get_connection
from backend.storage import DATA_DIR, prepare_storage

AUDIO_DIR = DATA_DIR / "audio"

VOICE_DE_MALE = "de-DE-ConradNeural"
VOICE_DE_FEMALE = "de-DE-KatjaNeural"
VOICE_UK = "uk-UA-OstapNeural"


def get_audio_filename(text: str, voice: str, rate: str) -> str:
    key = f"{voice}|{rate}|{text.strip()}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
    return f"{digest}.mp3"


async def synthesize_text(
    text: str, voice: str = VOICE_DE_MALE, rate: str = "+0%", *, force: bool = False
) -> str:
    prepare_storage()
    filename = get_audio_filename(text, voice, rate)
    filepath = AUDIO_DIR / filename

    if not force and filepath.exists() and filepath.stat().st_size > 200:
        return f"/audio/{filename}"

    temporary = AUDIO_DIR / f".{uuid4().hex}.part"
    try:
        communicate = edge_tts.Communicate(text=text.strip(), voice=voice, rate=rate)
        await communicate.save(str(temporary))
        if temporary.stat().st_size <= 200:
            raise ValueError("Отримано неповний MP3")
        temporary.replace(filepath)
    finally:
        temporary.unlink(missing_ok=True)
    return f"/audio/{filename}"


async def generate_missing_audio_all(force: bool = False, *, sentence_ids: list[int] | None = None) -> dict:
    targets = None if sentence_ids is None else set(sentence_ids)
    stats = {"generated": 0, "failed": 0, "total_checked": 0, "failed_sentence_ids": []}
    if targets == set():
        return stats
    with closing(get_connection()) as conn:
        rows = conn.execute("SELECT * FROM sentences ORDER BY id").fetchall()

    for row in rows:
        sentence_id = row["id"]
        if targets is not None and sentence_id not in targets:
            continue
        voice = VOICE_DE_MALE if sentence_id % 2 else VOICE_DE_FEMALE
        tracks = [
            ("audio_de_normal", "de", voice, "+0%"),
            ("audio_de_slow", "de", voice, "-22%"),
            ("audio_uk", "uk", VOICE_UK, "+5%"),
        ]
        pending = [
            track for track in tracks if force or not row[track[0]]
            or not (AUDIO_DIR / row[track[0]].rsplit("/", 1)[-1]).is_file()
        ]
        if not pending:
            continue
        stats["total_checked"] += 1
        failed = False
        for field, language, voice, rate in pending:
            try:
                url = await synthesize_text(row[language], voice, rate, force=force)
                with closing(get_connection()) as conn, conn:
                    conn.execute(
                        f"UPDATE sentences SET {field} = ? WHERE id = ? AND {language} = ?",
                        (url, sentence_id, row[language]),
                    )
            except Exception as error:
                print(f"[TTS Warning] Failed for sentence {sentence_id}: {error}")
                failed = True
        if failed:
            stats["failed_sentence_ids"].append(sentence_id)
        stats["failed" if failed else "generated"] += 1
    return stats
