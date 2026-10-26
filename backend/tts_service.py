import asyncio
import hashlib
from pathlib import Path
from typing import Dict, Optional
import edge_tts

from backend.database import get_connection, update_sentence_audio

BASE_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = BASE_DIR / "data" / "audio"

VOICE_DE_MALE = "de-DE-ConradNeural"
VOICE_DE_FEMALE = "de-DE-KatjaNeural"
VOICE_UK = "uk-UA-OstapNeural"


def get_audio_filename(text: str, voice: str, rate: str) -> str:
    key = f"{voice}|{rate}|{text.strip()}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
    return f"{digest}.mp3"


async def synthesize_text(
    text: str, voice: str = VOICE_DE_MALE, rate: str = "+0%"
) -> str:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    filename = get_audio_filename(text, voice, rate)
    filepath = AUDIO_DIR / filename

    if filepath.exists() and filepath.stat().st_size > 200:
        return f"/audio/{filename}"

    communicate = edge_tts.Communicate(text=text.strip(), voice=voice, rate=rate)
    await communicate.save(str(filepath))
    return f"/audio/{filename}"


async def generate_audio_for_sentence(
    sentence_id: int, de_text: str, uk_text: str, voice_de: str = VOICE_DE_MALE
) -> Dict[str, str]:
    de_normal_url = await synthesize_text(de_text, voice=voice_de, rate="+0%")
    de_slow_url = await synthesize_text(de_text, voice=voice_de, rate="-22%")
    uk_url = await synthesize_text(uk_text, voice=VOICE_UK, rate="+5%")

    update_sentence_audio(sentence_id, de_normal_url, de_slow_url, uk_url)
    return {
        "audio_de_normal": de_normal_url,
        "audio_de_slow": de_slow_url,
        "audio_uk": uk_url,
    }


async def generate_missing_audio_all(force: bool = False) -> Dict[str, int]:
    conn = get_connection()
    if force:
        rows = conn.execute("SELECT id, de, uk FROM sentences").fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, de, uk FROM sentences
            WHERE audio_de_normal = '' OR audio_de_normal IS NULL
               OR audio_de_slow = '' OR audio_de_slow IS NULL
               OR audio_uk = '' OR audio_uk IS NULL
            """
        ).fetchall()
    conn.close()

    generated = 0
    failed = 0
    for idx, row in enumerate(rows):
        # Alternate male/female German voices across sentences for better listening variety
        voice = VOICE_DE_MALE if idx % 2 == 0 else VOICE_DE_FEMALE
        try:
            await generate_audio_for_sentence(
                row["id"], row["de"], row["uk"], voice_de=voice
            )
            generated += 1
        except Exception as e:
            print(f"[TTS Warning] Failed for sentence {row['id']}: {e}")
            failed += 1

    return {"generated": generated, "failed": failed, "total_checked": len(rows)}
