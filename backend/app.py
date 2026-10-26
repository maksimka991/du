import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.database import (
    init_db,
    get_all_cards,
    get_known_vocabulary,
    import_pack_data,
    update_card_status,
)
from backend.tts_service import (
    AUDIO_DIR,
    synthesize_text,
    generate_missing_audio_all,
    VOICE_DE_MALE,
    VOICE_UK,
)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
STARTER_PACK_PATH = BASE_DIR / "data" / "packs" / "starter_pack.json"

app = FastAPI(title="Deutsch im Kontext — Навчальний додаток")


@app.middleware("http")
async def disable_static_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class CardStatusUpdate(BaseModel):
    mastery_level: Optional[int] = None
    is_favorite: Optional[int] = None


class PromptBuildRequest(BaseModel):
    mode: str = "word_list"  # "word_list" or "grammar_topic"
    category_name: str = "Нова підбірка"
    user_input: str
    include_known_vocab: bool = True


class PackImportRequest(BaseModel):
    json_text: str
    generate_tts: bool = True


class OnDemandTTSRequest(BaseModel):
    text: str
    lang: str = "de"
    slow: bool = False


@app.on_event("startup")
async def startup_event():
    init_db()
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    cards = get_all_cards()
    if not cards and STARTER_PACK_PATH.exists():
        try:
            pack_data = json.loads(STARTER_PACK_PATH.read_text(encoding="utf-8"))
            import_pack_data(pack_data)
            print("[Startup] Imported starter_pack.json into SQLite database.")
        except Exception as e:
            print(f"[Startup Warning] Could not import starter pack: {e}")


@app.get("/api/cards")
def api_get_cards(
    pack_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    cards = get_all_cards(pack_type=pack_type, category=category, search=search)
    all_cards = get_all_cards()
    categories = sorted(list({c["category"] for c in all_cards}))
    return {
        "cards": cards,
        "categories": categories,
        "total_cards": len(all_cards),
        "total_sentences": sum(len(c["sentences"]) for c in all_cards),
    }


@app.get("/api/vocab")
def api_get_vocab():
    vocab = get_known_vocabulary()
    return {"vocab": vocab, "count": len(vocab)}


@app.patch("/api/cards/{card_id}")
def api_update_card(card_id: int, payload: CardStatusUpdate):
    update_card_status(
        card_id=card_id,
        mastery_level=payload.mastery_level,
        is_favorite=payload.is_favorite,
    )
    return {"ok": True}


@app.post("/api/build-prompt")
def api_build_prompt(req: PromptBuildRequest):
    vocab = get_known_vocabulary() if req.include_known_vocab else []
    known_words_str = (
        ", ".join(f"{v['headword']} ({v['translation']})" for v in vocab)
        if vocab
        else "Базова лексика A1–A2"
    )

    mode_label = (
        "Список слів для вивчення у різних формах"
        if req.mode == "word_list"
        else "Граматична підтема (спецтема)"
    )

    prompt = f"""Ти — експертний викладач німецької мови та лінгвіст. Створи навчальний JSON-пакет для додатку вивчення німецької мови в контексті речень.

РЕЖИМ: {mode_label}
КАТЕГОРІЯ / ПІДТЕМА: {req.category_name}
ЗАВДАННЯ ВІД КОРИСТУВАЧА:
{req.user_input.strip()}

АКТИВНИЙ СЛОВНИК КОРИСТУВАЧА (Метод i+1 — обов'язково вплітай ці вже знайомі слова в речення разом із новими словами!):
{known_words_str}

ПОКРОКОВИЙ ПЛАН ТА ВИМОГИ ДО ГЕНЕРАЦІЇ:
1. Для кожного цільового слова створи окрему картку (`cards`) з 3 реченнями прогресивної складності:
   - `"просте"` (A1–A2): 4–7 слів, прямий або питальний порядок слів, базова форма (Nominativ або базовий Präsens).
   - `"середнє"` (A2–B1): зміна форми слова (Akkusativ / Dativ / множина) та обов'язкова рамкова конструкція речення (Satzklammer: Perfekt `haben/sein ... Partizip II`, Präteritum або модальне дієслово).
   - `"складніше"` (B1–B2): складнопідрядне речення зі сполучником (`damit`, `weil`, `obwohl`, `wenn`, `dass`) або інфінітивним зворотом (`um ... zu`), де дієслово стоїть у кінці, або подвійне керування (`Dativ + Akkusativ`).
2. ЗОЛОТЕ ПРАВИЛО ПЕРЕХРЕСНИХ РЕЧЕНЬ (Cross-Pollination): обов'язково роби перехресні речення зі слів із словника користувача! Кожне згенероване речення для цільового слова має одночасно включати ще 2–4 слова з поточного списку або з активного словника користувача (щоб при прослуховуванні одного речення користувач повторював одразу кілька своїх слів у взаємодії). Усі ці супутні слова також додавай у масив `tokens`.
3. У полі `complexity_notes` напиши 2–3 конкретні пункти розбору:
   - Синтаксис і рамка речення (Satzklammer): що на 2-му місці, а що в кінці і чому.
   - Відмінок і закінчення цільового слова саме в цьому реченні.
   - Сталі вирази або керування дієслова (Rektion).
4. У полі `tokens` розбери кожне важливе слово в реченні (іменники, дієслова, сполучники):
   - `pos`: `"noun_m"` (der), `"noun_f"` (die), `"noun_n"` (das), `"noun_pl"` (множина), `"verb"` (дієслово), `"conj"` (сполучник/прийменник).
   - `context_role`: коротка роль і відмінок у цьому реченні (напр. `"Akkusativ · Однина (meinen Schlüssel) — прямий додаток від vergessen"`).
   - `frame_id`: якщо два слова утворюють рамку речення (напр. `habe` і `vergessen`, або `Kannst` і `geben`, або `damit` і `öffnen kann`), дай їм однаковий `frame_id` (`"frame_1"`, `"frame_2"`).
   - `popup`:
     * Для іменника (`"type": "noun"`): `singular_nom` ("der Schlüssel"), `plural_nom` ("die Schlüssel"), `context_case` ("Akkusativ · Однина").
     * Для дієслова (`"type": "verb"`): `infinitive` ("geben"), `praesens` ("du g[i]bst" — якщо в 2 особі однини змінюється коренева голосна e→i/ie чи a→ä, візьми змінену букву в квадратні дужки `[...]`), `praeteritum` ("du gabst"), `perfekt` ("hat gegeben"), `note` (пояснення чергування або Perfekt), та масив `constructions` (`[{{"pattern": "jemandem etwas geben · Dativ + Akkusativ", "meaning": "дати комусь щось"}}]`).

Поверни ВИКЛЮЧНО валідний JSON за такою структурою:
{{
  "pack_title": "{req.category_name}",
  "category": "{req.category_name}",
  "pack_type": "{req.mode}",
  "description": "Згенеровано за списком користувача",
  "cards": [
    {{
      "headword": "der Schlüssel",
      "translation": "ключ",
      "category": "{req.category_name}",
      "part_of_speech": "noun",
      "gender": "m",
      "plural": "die Schlüssel",
      "forms_summary": "der Schlüssel (Nom) · den Schlüssel (Akk) · dem Schlüssel (Dat) · pl: die Schlüssel",
      "sentences": [
        {{
          "level": "просте",
          "de": "Wo ist mein Schlüssel?",
          "uk": "Де мій ключ?",
          "source": "Створено для навчання",
          "grammar_tags": ["Nominativ", "W-Frage"],
          "complexity_notes": ["Пояснення 1", "Пояснення 2"],
          "tokens": [
            {{
              "word": "Schlüssel",
              "pos": "noun_m",
              "context_role": "Nominativ · Однина — підмет",
              "popup": {{
                "type": "noun",
                "singular_nom": "der Schlüssel",
                "plural_nom": "die Schlüssel",
                "context_case": "Nominativ · Однина"
              }}
            }}
          ]
        }}
      ]
    }}
  ]
}}"""
    return {"prompt": prompt, "known_words_count": len(vocab)}


@app.post("/api/import-pack")
async def api_import_pack(req: PackImportRequest):
    raw = req.json_text.strip()
    # Strip markdown code fences if user pasted ```json ... ```
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    try:
        pack_data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400, detail=f"Помилка формату JSON: {str(e)}"
        )

    if "cards" not in pack_data or not isinstance(pack_data["cards"], list):
        raise HTTPException(
            status_code=400,
            detail="У JSON відсутній масив 'cards'. Перевірте структуру пакету.",
        )

    result = import_pack_data(pack_data)
    tts_stats = {"generated": 0, "failed": 0}
    if req.generate_tts:
        tts_stats = await generate_missing_audio_all(force=False)

    return {"ok": True, "import": result, "tts": tts_stats}


@app.post("/api/generate-audio")
async def api_generate_audio(force: bool = False):
    stats = await generate_missing_audio_all(force=force)
    return {"ok": True, "stats": stats}


@app.post("/api/tts")
async def api_tts_single(req: OnDemandTTSRequest):
    voice = VOICE_DE_MALE if req.lang == "de" else VOICE_UK
    rate = "-22%" if req.slow else "+0%"
    try:
        url = await synthesize_text(req.text, voice=voice, rate=rate)
        return {"ok": True, "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
