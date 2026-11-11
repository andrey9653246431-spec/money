from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from design_factory.brand import Brand
from design_factory.models import ContentError, load_posts
from design_factory.renderer import render_avatar, render_post
from design_factory.text import fit_text, wrap_text

ROOT = Path(__file__).resolve().parents[1]


def test_examples_load() -> None:
    posts = load_posts(ROOT / "examples" / "posts.json")
    assert len(posts) == 3
    assert [post.slot for post in posts] == ["morning", "day", "evening"]
    assert len(posts[1].card.points) == 3


def test_too_many_points_rejected(tmp_path: Path) -> None:
    payload = {
        "date": "2026-11-12",
        "posts": [
            {
                "slot": "day",
                "rubric": "Тест",
                "card": {"title": "Тест", "points": ["1", "2", "3", "4"]},
            }
        ],
    }
    source = tmp_path / "bad.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ContentError, match="не более 3"):
        load_posts(source)


def test_text_wrap_respects_width() -> None:
    brand = Brand(ROOT)
    image = Image.new("RGB", (1080, 1350))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    layout = fit_text(
        draw,
        "Спокойный заголовок о личных финансах без лишней тревоги",
        brand.font_path,
        max_size=72,
        min_size=44,
        max_width=700,
        max_height=400,
        max_lines=4,
        weight=800,
    )
    assert 1 < len(layout.lines) <= 4
    assert layout.height <= 400
    for line in layout.lines:
        assert draw.textlength(line, font=layout.font) <= 700
    assert wrap_text(draw, "", layout.font, 700) == [""]


@pytest.mark.parametrize("index", [0, 1, 2])
def test_render_examples(index: int) -> None:
    brand = Brand(ROOT)
    post = load_posts(ROOT / "examples" / "posts.json")[index]
    image = render_post(post, brand, index)
    assert image.size == (1080, 1350)
    assert image.mode == "RGB"
    assert len(image.getcolors(maxcolors=10_000_000)) > 20


def test_build_files_and_avatar(tmp_path: Path) -> None:
    brand = Brand(ROOT)
    posts = load_posts(ROOT / "examples" / "posts.json")
    for index, post in enumerate(posts):
        render_post(post, brand, index).save(tmp_path / f"{index}.png")
    render_avatar(brand).save(tmp_path / "avatar.png")
    assert Image.open(tmp_path / "avatar.png").size == (1024, 1024)
    assert len(list(tmp_path.glob("*.png"))) == 4


def test_horoscope_variant_renders() -> None:
    brand = Brand(ROOT)
    post = load_posts(ROOT / "examples" / "posts.json")[2]
    horoscope = type(post)(
        content_id="horoscope-demo",
        date=post.date,
        slot="evening",
        rubric="Финансовый гороскоп",
        card=post.card,
        image_prompt=post.image_prompt,
        alt_text=post.alt_text,
    )
    assert horoscope.is_horoscope
    assert render_post(horoscope, brand).size == (1080, 1350)


def test_excessive_text_fails_instead_of_clipping() -> None:
    brand = Brand(ROOT)
    post = load_posts(ROOT / "examples" / "posts.json")[0]
    huge = "Очень длинный заголовок " * 100
    changed = type(post)(
        content_id=post.content_id,
        date=post.date,
        slot=post.slot,
        rubric=post.rubric,
        card=type(post.card)(title=huge),
        image_prompt=post.image_prompt,
        alt_text=post.alt_text,
    )
    with pytest.raises(ValueError, match="не помещается"):
        render_post(changed, brand)
