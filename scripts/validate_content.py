from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

SLOTS = {"morning", "day", "evening"}
REQUIRED_GATE = {
    "facts_checked",
    "style_cleaned",
    "authorial_voice_checked",
    "natural_opening_checked",
    "final_checklist_passed",
}
BANNED = (
    "в современном мире",
    "сегодня поговорим",
    "важно отметить",
    "стоит учесть",
    "критично помнить",
    "по словам экспертов",
    "некоторые критики",
    "подводя итог",
    "в заключение",
    "по состоянию на",
    "на момент моего обучения",
    "в доступных источниках",
)
HIGH_RISK = ("акци", "скидк", "кредит", "рассроч", "цифров", "налог", "мошен", "страхов")


def content_id(post: dict, date: str, index: int) -> str:
    return str(post.get("content_id") or f"{date}-{index + 1:02d}-{post.get('slot', 'post')}")


def validate_payload(
    payload: object, slot: str | None, require_approved: bool
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return ["Корень JSON должен быть объектом"], warnings
    date = payload.get("date", "")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except (TypeError, ValueError):
        errors.append("date: нужен формат YYYY-MM-DD")
    posts = payload.get("posts")
    if not isinstance(posts, list) or not posts:
        return errors + ["posts: нужен непустой массив"], warnings
    seen_slots: set[str] = set()
    seen_ids: set[str] = set()
    selected = 0
    for index, post in enumerate(posts):
        if not isinstance(post, dict):
            errors.append(f"posts[{index}]: ожидался объект")
            continue
        post_slot = post.get("slot")
        cid = content_id(post, str(date), index)
        prefix = f"{cid}"
        if post_slot not in SLOTS:
            errors.append(f"{prefix}: slot должен быть morning/day/evening")
        elif post_slot in seen_slots:
            errors.append(f"{prefix}: слот {post_slot} повторяется")
        else:
            seen_slots.add(post_slot)
        if slot and post_slot == slot:
            selected += 1
        if cid in seen_ids:
            errors.append(f"{prefix}: content_id повторяется")
        seen_ids.add(cid)
        for field in ("rubric", "telegram_text", "max_text"):
            if not isinstance(post.get(field), str) or not post.get(field, "").strip():
                errors.append(f"{prefix}: {field} обязателен")
        card = post.get("card")
        if not isinstance(card, dict) or not str(card.get("title", "")).strip():
            errors.append(f"{prefix}: card.title обязателен")
        elif len(card.get("points", [])) > 3:
            errors.append(f"{prefix}: не более трёх card.points")
        text = str(post.get("telegram_text", ""))
        folded = text.casefold()
        for phrase in BANNED:
            if phrase in folded:
                errors.append(f"{prefix}: запрещённая фраза «{phrase}»")
        if re.search(r"[?&]utm_[^=]*=", text, flags=re.I):
            errors.append(f"{prefix}: UTM в telegram_text")
        if re.search(r"(^|\n)\s{0,3}#{1,6}\s|\*\*|__|(^|\n)\s*---\s*(\n|$)", text):
            errors.append(f"{prefix}: Markdown-разметка в telegram_text")
        for fact in post.get("unconfirmed_facts", []):
            if isinstance(fact, str) and len(fact) > 12 and fact.casefold() in folded:
                errors.append(f"{prefix}: неподтверждённый факт включён в текст")
        gate = post.get("quality_gate")
        if not isinstance(gate, dict):
            errors.append(f"{prefix}: quality_gate обязателен")
        else:
            for key in REQUIRED_GATE:
                if gate.get(key) is not True:
                    errors.append(f"{prefix}: quality_gate.{key} != true")
        if require_approved:
            if post.get("status") != "approved":
                errors.append(f"{prefix}: status != approved")
            if not str(post.get("reviewer", "")).strip():
                errors.append(f"{prefix}: reviewer обязателен")
            if not str(post.get("approved_at", "")).strip():
                errors.append(f"{prefix}: approved_at обязателен")
        sources = post.get("source_urls", [])
        if not isinstance(sources, list):
            errors.append(f"{prefix}: source_urls должен быть массивом")
            sources = []
        for url in sources:
            parsed = urlparse(str(url))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(f"{prefix}: некорректный источник {url!r}")
            if re.search(r"[?&]utm_[^=]*=", str(url), flags=re.I):
                errors.append(f"{prefix}: UTM в source_urls")
        risk_text = f"{post.get('rubric', '')} {post.get('working_title', '')}".casefold()
        if (
            any(word in risk_text for word in HIGH_RISK)
            and post.get("manual_review_required") is not True
        ):
            errors.append(f"{prefix}: для финансовой темы manual_review_required=true обязателен")
        limits = {"morning": (250, 500), "day": (700, 1200), "evening": (450, 800)}
        if post_slot in limits:
            low, high = limits[post_slot]
            if "гороскоп" in str(post.get("rubric", "")).casefold():
                high = 1800
            if not low <= len(text) <= high:
                warnings.append(f"{prefix}: длина {len(text)} вне рекомендации {low}–{high}")
    if slot and selected != 1:
        errors.append(f"В файле должен быть ровно один пост слота {slot}")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--slot", choices=sorted(SLOTS))
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()
    try:
        payload = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Ошибка чтения JSON: {error}", file=sys.stderr)
        return 2
    errors, warnings = validate_payload(payload, args.slot, args.require_approved)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(f"Проверка не пройдена: {len(errors)} ошибок", file=sys.stderr)
        return 1
    print(f"OK: {args.file}; слот={args.slot or 'все'}; approval={args.require_approved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
