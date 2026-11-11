from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ALLOWED_SLOTS = {"morning", "day", "evening"}


class ContentError(ValueError):
    """Input content is incomplete or inconsistent."""


@dataclass(frozen=True)
class Card:
    title: str
    subtitle: str = ""
    badge: str = ""
    points: list[str] = field(default_factory=list)
    footer: str = ""


@dataclass(frozen=True)
class Post:
    content_id: str
    date: str
    slot: str
    rubric: str
    card: Card
    image_prompt: str
    alt_text: str

    @property
    def is_horoscope(self) -> bool:
        return "гороскоп" in self.rubric.casefold()


def _text(value: Any, field_name: str, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ContentError(f"{field_name}: ожидалась строка")
    value = " ".join(value.split())
    if required and not value:
        raise ContentError(f"{field_name}: поле обязательно")
    return value


def parse_post(raw: dict[str, Any], date: str, index: int) -> Post:
    if not isinstance(raw, dict):
        raise ContentError(f"posts[{index}]: ожидался объект")
    slot = _text(raw.get("slot"), f"posts[{index}].slot", required=True)
    if slot not in ALLOWED_SLOTS:
        raise ContentError(f"posts[{index}].slot: допустимы morning, day, evening")
    rubric = _text(raw.get("rubric"), f"posts[{index}].rubric", required=True)
    card_raw = raw.get("card") or {}
    if not isinstance(card_raw, dict):
        raise ContentError(f"posts[{index}].card: ожидался объект")
    title = _text(card_raw.get("title"), f"posts[{index}].card.title")
    if not title:
        title = _text(raw.get("working_title"), f"posts[{index}].working_title", required=True)
    points_raw = card_raw.get("points") or []
    if not isinstance(points_raw, list):
        raise ContentError(f"posts[{index}].card.points: ожидался массив")
    if len(points_raw) > 3:
        raise ContentError(f"posts[{index}].card.points: на карточке допустимо не более 3 пунктов")
    points = [
        _text(point, f"posts[{index}].card.points[{point_index}]", required=True)
        for point_index, point in enumerate(points_raw)
    ]
    content_id = _text(raw.get("content_id"), f"posts[{index}].content_id")
    return Post(
        content_id=content_id or f"{date}-{index + 1:02d}-{slot}",
        date=date,
        slot=slot,
        rubric=rubric,
        card=Card(
            title=title,
            subtitle=_text(card_raw.get("subtitle"), f"posts[{index}].card.subtitle"),
            badge=_text(card_raw.get("badge"), f"posts[{index}].card.badge") or rubric.upper(),
            points=points,
            footer=_text(card_raw.get("footer"), f"posts[{index}].card.footer"),
        ),
        image_prompt=_text(raw.get("image_prompt"), f"posts[{index}].image_prompt"),
        alt_text=_text(raw.get("alt_text"), f"posts[{index}].alt_text") or title,
    )


def load_posts(path: str | Path) -> list[Post]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ContentError(f"Файл не найден: {source}") from None
    except json.JSONDecodeError as error:
        raise ContentError(f"Некорректный JSON: {error}") from None
    if not isinstance(payload, dict):
        raise ContentError("Корень JSON должен быть объектом")
    date = _text(payload.get("date"), "date", required=True)
    posts_raw = payload.get("posts")
    if not isinstance(posts_raw, list) or not posts_raw:
        raise ContentError("posts: нужен непустой массив")
    return [parse_post(raw, date, index) for index, raw in enumerate(posts_raw)]
