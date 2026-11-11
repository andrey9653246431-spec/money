from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from design_factory.brand import Brand
from design_factory.models import load_posts
from design_factory.renderer import render_post
from scripts.generate_content import (
    compose_text,
    generate_payload,
    load_library,
    write_generated,
)
from scripts.publish_telegram import CHANNEL_FOOTER, full_text
from scripts.validate_content import validate_payload

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "content" / "generator" / "library.json"


def test_generator_creates_valid_renderable_day(tmp_path: Path) -> None:
    output = tmp_path / "2026-11-13.json"
    write_generated(LIBRARY, output, date(2026, 11, 13))
    payload = json.loads(output.read_text(encoding="utf-8"))
    errors, warnings = validate_payload(payload, None, require_approved=True)
    assert errors == []
    assert warnings == []
    assert [post["slot"] for post in payload["posts"]] == ["morning", "day", "evening"]
    assert all(CHANNEL_FOOTER not in post["telegram_text"] for post in payload["posts"])
    assert all(full_text(post).endswith(CHANNEL_FOOTER) for post in payload["posts"])
    brand = Brand(ROOT)
    for index, post in enumerate(load_posts(output)):
        assert render_post(post, brand, index).size == (1080, 1350)


def test_generation_is_deterministic_and_does_not_overwrite(tmp_path: Path) -> None:
    first = tmp_path / "first" / "2026-11-13.json"
    second = tmp_path / "second" / "2026-11-13.json"
    write_generated(LIBRARY, first, date(2026, 11, 13))
    write_generated(LIBRARY, second, date(2026, 11, 13))
    first_payload = json.loads(first.read_text(encoding="utf-8"))
    second_payload = json.loads(second.read_text(encoding="utf-8"))
    assert [post["generator_variant_id"] for post in first_payload["posts"]] == [
        post["generator_variant_id"] for post in second_payload["posts"]
    ]
    with pytest.raises(FileExistsError):
        write_generated(LIBRARY, first, date(2026, 11, 13))


def test_every_library_variant_meets_length_and_content_rules() -> None:
    library = load_library(LIBRARY)
    limits = {"morning": (250, 500), "day": (700, 1200), "evening": (450, 800)}
    for topic in library["topics"]:
        for variant in range(len(topic["openings"]) * len(topic["closings"])):
            text = compose_text(topic, variant)
            low, high = limits[topic["slot"]]
            if "гороскоп" in topic["rubric"].casefold():
                high = 1800
                assert "Развлекательный формат, а не финансовая рекомендация" in text
            assert low <= len(text) <= high, (topic["topic_id"], variant, len(text))


def test_history_prevents_exact_repeats_until_pool_is_used(tmp_path: Path) -> None:
    library = load_library(LIBRARY)
    seen = {"morning": set(), "day": set(), "evening": set()}
    start = date(2026, 11, 13)
    for offset in range(30):
        current = start + timedelta(days=offset)
        payload = generate_payload(library, current, tmp_path)
        for post in payload["posts"]:
            variant = post["generator_variant_id"]
            assert variant not in seen[post["slot"]]
            seen[post["slot"]].add(variant)
        (tmp_path / f"{current}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_sunday_uses_only_disclaimed_horoscope(tmp_path: Path) -> None:
    library = load_library(LIBRARY)
    payload = generate_payload(library, date(2026, 11, 15), tmp_path)
    evening = payload["posts"][2]
    assert "гороскоп" in evening["rubric"].casefold()
    assert "Развлекательный формат, а не финансовая рекомендация" in evening["telegram_text"]
    assert "инвестиц" not in evening["telegram_text"].casefold()
