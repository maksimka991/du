import argparse
import asyncio
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from backend.database import init_db, import_pack_data, get_known_vocabulary
from backend.tts_service import generate_missing_audio_all


def cmd_import(file_path: str, run_tts: bool) -> None:
    path = Path(file_path)
    if not path.exists():
        print(f"[Error] File not found: {path}")
        sys.exit(1)

    pack_data = json.loads(path.read_text(encoding="utf-8"))
    res = import_pack_data(pack_data)
    print(
        f"[OK] Imported pack #{res['pack_id']}: "
        f"{res['imported_cards']} cards, {res['imported_sentences']} sentences."
    )
    if run_tts:
        print("[TTS] Generating MP3 audio files via Edge-TTS...")
        stats = asyncio.run(generate_missing_audio_all(force=False))
        print(
            f"[TTS OK] Generated: {stats['generated']}, Failed: {stats['failed']} "
            f"(Total checked: {stats['total_checked']})"
        )


def cmd_export_vocab() -> None:
    init_db()
    vocab = get_known_vocabulary()
    if not vocab:
        print("База слів порожня.")
        return
    print(f"Активний словник користувача ({len(vocab)} слів):")
    for item in vocab:
        print(
            f"- {item['headword']} — {item['translation']} "
            f"[{item['category']}]"
        )


def cmd_tts(force: bool) -> None:
    init_db()
    print("[TTS] Generating audio for sentences...")
    stats = asyncio.run(generate_missing_audio_all(force=force))
    print(f"[TTS OK] {stats}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI для управління навчальними пакетами та озвучкою"
    )
    sub = parser.add_subparsers(dest="command")

    p_import = sub.add_parser("import", help="Імпортувати JSON-пакет у базу даних")
    p_import.add_argument("file", help="Шлях до JSON-файлу пакету")
    p_import.add_argument(
        "--tts", action="store_true", help="Одразу згенерувати MP3 озвучку"
    )

    sub.add_parser(
        "export-vocab", help="Вивести список усіх відомих слів користувача (i+1)"
    )

    p_tts = sub.add_parser("tts", help="Згенерувати відсутні MP3-файли озвучки")
    p_tts.add_argument(
        "--force", action="store_true", help="Перегенерувати всі аудіофайли"
    )

    args = parser.parse_args()
    if args.command == "import":
        cmd_import(args.file, args.tts)
    elif args.command == "export-vocab":
        cmd_export_vocab()
    elif args.command == "tts":
        cmd_tts(args.force)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
