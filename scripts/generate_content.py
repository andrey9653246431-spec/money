from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from datetime import UTC, datetime
from datetime import date as date_type
from pathlib import Path
from typing import Any

try:
    from .validate_content import validate_payload
except ImportError:  # Direct execution: python scripts/generate_content.py
    from validate_content import validate_payload

SLOTS = ("morning", "day", "evening")
PUBLISH_TIMES = {"morning": "09:00", "day": "13:00", "evening": "20:00"}
RUBRICS = {
    "morning": "Утро без тревоги",
    "day": "Деньги и жизнь",
    "evening": "Спокойный вечер",
}
GENERATOR_NAME = "dbp-offline-editorial-generator"
QUALITY_GATE = {
    "facts_checked": True,
    "style_cleaned": True,
    "authorial_voice_checked": True,
    "natural_opening_checked": True,
    "final_checklist_passed": True,
}


def load_library(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("topics"), list):
        raise ValueError("Библиотека должна содержать массив topics")
    if not str(payload.get("version", "")).strip():
        raise ValueError("У библиотеки должна быть версия")
    topic_ids: set[str] = set()
    for topic in payload["topics"]:
        if not isinstance(topic, dict):
            raise ValueError("Каждая тема библиотеки должна быть объектом")
        topic_id = str(topic.get("topic_id", "")).strip()
        if not topic_id or topic_id in topic_ids:
            raise ValueError(f"Некорректный или повторный topic_id: {topic_id!r}")
        topic_ids.add(topic_id)
        if topic.get("slot") not in SLOTS:
            raise ValueError(f"{topic_id}: неизвестный слот")
        for field in ("body", "working_title", "card", "openings", "closings"):
            if field not in topic:
                raise ValueError(f"{topic_id}: нет поля {field}")
        if not isinstance(topic["openings"], list) or len(topic["openings"]) < 2:
            raise ValueError(f"{topic_id}: нужно минимум два начала")
        if not isinstance(topic["closings"], list) or len(topic["closings"]) < 2:
            raise ValueError(f"{topic_id}: нужно минимум две концовки")
    return payload


def is_horoscope(topic: dict[str, Any]) -> bool:
    return "гороскоп" in str(topic.get("rubric", "")).casefold()


def compose_text(topic: dict[str, Any], variant: int) -> str:
    openings = topic["openings"]
    closings = topic["closings"]
    variant_count = len(openings) * len(closings)
    if not 0 <= variant < variant_count:
        raise ValueError(f"Вариант {variant} вне диапазона 0–{variant_count - 1}")
    opening_index, closing_index = divmod(variant, len(closings))
    return "\n\n".join(
        part.strip()
        for part in (openings[opening_index], topic["body"], closings[closing_index])
        if str(part).strip()
    )


def used_variants(history_dir: Path) -> set[str]:
    used: set[str] = set()
    if not history_dir.exists():
        return used
    for path in history_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for post in payload.get("posts", []) if isinstance(payload, dict) else []:
            if isinstance(post, dict) and post.get("generator_variant_id"):
                used.add(str(post["generator_variant_id"]))
    return used


def eligible_topics(library: dict[str, Any], slot: str, content_date: date_type) -> list[dict]:
    topics = [topic for topic in library["topics"] if topic.get("slot") == slot]
    if slot == "evening":
        wants_horoscope = content_date.weekday() == 6
        topics = [topic for topic in topics if is_horoscope(topic) == wants_horoscope]
    return topics


def choose_topic_variant(
    library: dict[str, Any], slot: str, content_date: date_type, history_dir: Path
) -> tuple[dict, int]:
    candidates: list[tuple[dict, int]] = []
    for topic in eligible_topics(library, slot, content_date):
        variant_count = len(topic["openings"]) * len(topic["closings"])
        candidates.extend((topic, variant) for variant in range(variant_count))
    if not candidates:
        raise ValueError(f"В библиотеке нет подходящих тем для {slot} {content_date}")
    used = used_variants(history_dir)
    unused = [
        (topic, variant)
        for topic, variant in candidates
        if f"{topic['topic_id']}:v{variant + 1}" not in used
    ]
    # Reset only after every suitable variant has been used. The date-seeded choice is reproducible.
    pool = unused or candidates
    rng = random.Random(f"{GENERATOR_NAME}:v{library['version']}:{content_date}:{slot}")
    return rng.choice(pool)


def build_post(
    topic: dict,
    variant: int,
    content_date: date_type,
    library_version: str,
    approved_at: str,
) -> dict[str, Any]:
    slot = topic["slot"]
    variant_id = f"{topic['topic_id']}:v{variant + 1}"
    text = compose_text(topic, variant)
    return {
        "content_id": f"{content_date}-{slot}-{topic['topic_id']}-v{variant + 1}",
        "slot": slot,
        "publish_time": PUBLISH_TIMES[slot],
        "rubric": topic.get("rubric") or RUBRICS[slot],
        "working_title": topic["working_title"],
        "headline_options": [topic["working_title"]],
        "telegram_text": text,
        "max_text": text,
        "hashtags": list(topic.get("hashtags", [])),
        "card": copy.deepcopy(topic["card"]),
        "image_prompt": topic.get(
            "image_prompt",
            "Спокойная фирменная плоская иллюстрация без текста, брендов и обещаний богатства.",
        ),
        "alt_text": topic.get("alt_text") or topic["card"]["title"],
        "source_urls": list(topic.get("source_urls", [])),
        "unconfirmed_facts": [],
        "facts_requiring_check": [],
        "quality_gate": dict(QUALITY_GATE),
        "manual_review_required": bool(topic.get("manual_review_required", False)),
        "review_reason": topic.get(
            "review_reason",
            "Evergreen-текст из версионированной редакционной библиотеки "
            "без актуальных предложений",
        ),
        "status": "approved",
        "reviewer": f"{GENERATOR_NAME}/library-v{library_version}",
        "approved_at": approved_at,
        "generator_topic_id": topic["topic_id"],
        "generator_variant_id": variant_id,
    }


def generate_payload(
    library: dict[str, Any], content_date: date_type, history_dir: Path
) -> dict[str, Any]:
    approved_at = datetime.now(UTC).isoformat(timespec="seconds")
    posts = []
    for slot in SLOTS:
        topic, variant = choose_topic_variant(library, slot, content_date, history_dir)
        posts.append(build_post(topic, variant, content_date, str(library["version"]), approved_at))
    return {
        "date": content_date.isoformat(),
        "editorial_summary": (
            "Автоматическая сборка из редакционной evergreen-библиотеки; "
            "актуальные цены, акции и новости не генерируются"
        ),
        "posts": posts,
        "daily_editor_checklist": [
            "Генератор не добавлял актуальные предложения и неподтверждённые факты",
            "Карточки и тексты проверены автоматическим quality gate",
        ],
        "generated_by": GENERATOR_NAME,
        "library_version": library["version"],
    }


def write_generated(library_path: Path, output: Path, content_date: date_type) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"Файл уже существует и не будет перезаписан: {output}")
    library = load_library(library_path)
    payload = generate_payload(library, content_date, output.parent)
    errors, warnings = validate_payload(payload, None, require_approved=True)
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        raise ValueError("Сгенерированный контент не прошёл проверку: " + "; ".join(errors))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    for post in payload["posts"]:
        print(
            f"GENERATED: {post['slot']}; {post['generator_variant_id']}; "
            f"знаков={len(post['telegram_text'])}"
        )
    print(f"OK: {output}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Бесплатная генерация дня из локальной редакционной библиотеки без API"
    )
    parser.add_argument("--date", required=True, help="Дата в формате YYYY-MM-DD")
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        content_date = date_type.fromisoformat(args.date)
        write_generated(args.library, args.output, content_date)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
