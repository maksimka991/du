import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, ValidationError

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PackType = Literal["word_list", "grammar_topic"]


class Popup(BaseModel):
    type: str = ""
    title: str = ""
    explanation: str = ""
    footer_summary: str = ""
    singular_nom: str = ""
    plural_nom: str = ""
    context_case: str = ""
    infinitive: str = ""
    praesens: str = ""
    praeteritum: str = ""
    perfekt: str = ""
    note: str = ""
    constructions: list[dict[str, str]] = Field(default_factory=list)


class Token(BaseModel):
    word: Text
    pos: str = ""
    context_role: str = ""
    frame_id: str | None = None
    popup: Popup | None = None


class Sentence(BaseModel):
    level: Text = "просте"
    de: Text
    uk: Text
    source: str = "Створено для навчання"
    grammar_tags: list[str] = Field(default_factory=list)
    complexity_notes: list[str] = Field(default_factory=list)
    tokens: list[Token] = Field(default_factory=list)


class Card(BaseModel):
    headword: Text
    translation: str = ""
    category: str | None = None
    pack_type: PackType | None = None
    part_of_speech: str = ""
    gender: str = ""
    plural: str = ""
    forms_summary: str = ""
    sentences: list[Sentence] = Field(min_length=1)


class Pack(BaseModel):
    pack_title: Text = "Навчальний набір"
    category: Text = "Загальне"
    pack_type: PackType = "word_list"
    description: str = ""
    cards: list[Card] = Field(min_length=1)


def parse_pack(raw: str) -> Pack:
    raw = raw.strip()
    lines = raw.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1] == "```":
        raw = "\n".join(lines[1:-1])
    try:
        pack = Pack.model_validate(json.loads(raw))
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON, рядок {error.lineno}, стовпець {error.colno}: {error.msg}") from error
    except ValidationError as error:
        issues = []
        for issue in error.errors():
            path = "".join(f"[{key}]" if isinstance(key, int) else f".{key}" for key in issue["loc"])
            issues.append(f"{path.lstrip('.') or 'Пакет'}: {issue['msg']}")
        raise ValueError("\n".join(issues)) from error

    seen = set()
    for index, card in enumerate(pack.cards):
        key = (card.headword, card.category or pack.category)
        if key in seen:
            raise ValueError(f"cards[{index}].headword: картка вже є в цьому пакеті")
        seen.add(key)
    return pack
