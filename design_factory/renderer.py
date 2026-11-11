from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

from .brand import Brand
from .models import Post
from .text import draw_layout, fit_text, load_font


def _pill(
    draw: ImageDraw.ImageDraw, brand: Brand, text: str, xy: tuple[int, int], dark: bool
) -> None:
    x, y = xy
    font = load_font(brand.font_path, 21, 800)
    width = math.ceil(draw.textlength(text, font=font)) + 42
    fill = brand.color("mint") if dark else brand.color("navy")
    text_fill = brand.color("navy") if dark else brand.color("cream")
    draw.rounded_rectangle((x, y, x + width, y + 48), radius=24, fill=fill)
    draw.text((x + 21, y + 10), text, font=font, fill=text_fill)


def _header(image: Image.Image, brand: Brand, post: Post, dark: bool) -> None:
    draw = ImageDraw.Draw(image)
    foreground = brand.color("cream") if dark else brand.color("navy")
    draw.ellipse((64, 50, 112, 98), fill=brand.color("orange"))
    coin_font = load_font(brand.font_path, 28, 800)
    draw.text((76, 56), "₽", font=coin_font, fill=brand.color("navy"))
    brand_font = load_font(brand.font_path, 24, 800)
    draw.text((128, 60), brand.name, font=brand_font, fill=foreground)
    _pill(draw, brand, post.card.badge, (64, 142), dark)


def _footer(image: Image.Image, brand: Brand, post: Post, dark: bool) -> None:
    draw = ImageDraw.Draw(image)
    foreground = brand.color("cream") if dark else brand.color("navy")
    line = "#496173" if dark else brand.color("line")
    draw.line((64, 1210, 1016, 1210), fill=line, width=2)
    if post.card.footer:
        layout = fit_text(
            draw,
            post.card.footer,
            brand.font_path,
            max_size=25,
            min_size=21,
            max_width=760,
            max_height=44,
            max_lines=1,
            weight=600,
        )
        draw_layout(draw, layout, (64, 1240), foreground)
    date_font = load_font(brand.font_path, 21, 600)
    date_text = post.date
    width = draw.textlength(date_text, font=date_font)
    draw.text((1016 - width, 1242), date_text, font=date_font, fill=foreground)


def _title(
    image: Image.Image, brand: Brand, text: str, y: int, dark: bool, width: int = 920
) -> int:
    draw = ImageDraw.Draw(image)
    layout = fit_text(
        draw,
        text,
        brand.font_path,
        max_size=74,
        min_size=46,
        max_width=width,
        max_height=330,
        max_lines=4,
        weight=800,
    )
    color = brand.color("cream") if dark else brand.color("navy")
    return draw_layout(draw, layout, (64, y), color)


def _subtitle(
    image: Image.Image,
    brand: Brand,
    text: str,
    y: int,
    dark: bool,
    width: int = 880,
) -> int:
    if not text:
        return y
    draw = ImageDraw.Draw(image)
    layout = fit_text(
        draw,
        text,
        brand.font_path,
        max_size=34,
        min_size=27,
        max_width=width,
        max_height=155,
        max_lines=3,
        weight=500,
    )
    color = "#D7E6E2" if dark else brand.color("muted")
    return draw_layout(draw, layout, (64, y), color)


def _points(image: Image.Image, brand: Brand, post: Post, top: int, dark: bool) -> None:
    if not post.card.points:
        return
    draw = ImageDraw.Draw(image)
    panel_fill = "#21445C" if dark else brand.color("paper")
    outline = "#365B70" if dark else brand.color("line")
    draw.rounded_rectangle(
        (54, top, 1026, 1168), radius=38, fill=panel_fill, outline=outline, width=2
    )
    row_height = 126
    for index, point in enumerate(post.card.points):
        y = top + 38 + index * row_height
        circle_fill = brand.color("orange") if index == 0 else brand.color("mint")
        draw.ellipse((86, y, 134, y + 48), fill=circle_fill)
        number_font = load_font(brand.font_path, 23, 800)
        number = str(index + 1)
        number_width = draw.textlength(number, font=number_font)
        draw.text(
            (110 - number_width / 2, y + 8), number, font=number_font, fill=brand.color("navy")
        )
        layout = fit_text(
            draw,
            point,
            brand.font_path,
            max_size=31,
            min_size=25,
            max_width=820,
            max_height=86,
            max_lines=2,
            weight=600,
        )
        foreground = brand.color("cream") if dark else brand.color("navy")
        draw_layout(draw, layout, (158, y + 2), foreground)


def _wallet(image: Image.Image, brand: Brand, x: int, y: int) -> None:
    draw = ImageDraw.Draw(image)
    draw.ellipse((x - 120, y + 90, x + 40, y + 250), fill=brand.color("mint"))
    draw.rounded_rectangle((x, y + 40, x + 280, y + 230), radius=34, fill=brand.color("navy"))
    draw.rounded_rectangle((x + 22, y, x + 248, y + 120), radius=24, fill=brand.color("coral"))
    draw.rounded_rectangle(
        (x + 150, y + 92, x + 300, y + 172), radius=24, fill=brand.color("orange")
    )
    draw.ellipse((x + 180, y + 119, x + 202, y + 141), fill=brand.color("navy"))
    for dx, dy, radius in [(-30, 20, 34), (30, -25, 26), (82, -42, 20)]:
        draw.ellipse(
            (x + dx - radius, y + dy - radius, x + dx + radius, y + dy + radius),
            fill=brand.color("orange"),
        )


def _receipt(image: Image.Image, brand: Brand, x: int, y: int) -> None:
    draw = ImageDraw.Draw(image)
    draw.ellipse((x - 90, y + 20, x + 230, y + 340), fill=brand.color("mint"))
    draw.rounded_rectangle((x, y, x + 210, y + 300), radius=24, fill=brand.color("navy"))
    for index, width in enumerate((120, 142, 96)):
        line_y = y + 62 + index * 54
        draw.rounded_rectangle(
            (x + 34, line_y, x + 34 + width, line_y + 14), radius=7, fill=brand.color("cream")
        )
    draw.ellipse((x + 116, y + 218, x + 200, y + 302), fill=brand.color("orange"))
    font = load_font(brand.font_path, 44, 800)
    draw.text((x + 139, y + 229), "₽", font=font, fill=brand.color("navy"))


def _stars(image: Image.Image, brand: Brand, seed: int, horoscope: bool) -> None:
    draw = ImageDraw.Draw(image)
    rng = random.Random(seed)
    for _ in range(34 if horoscope else 20):
        if rng.random() < 0.45:
            x, y = rng.randint(610, 1030), rng.randint(110, 240)
        else:
            # Keep the right decorative strip clear of the title and subtitle.
            x, y = rng.randint(930, 1030), rng.randint(250, 700)
        radius = rng.choice((2, 3, 4, 6))
        color = brand.color("orange") if rng.random() > 0.55 else brand.color("mint")
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    draw.ellipse((820, 170, 970, 320), fill=brand.color("orange"))
    draw.ellipse((866, 138, 994, 288), fill=brand.color("navy_deep"))
    if horoscope:
        # The ring stays to the right of the two-line title area.
        draw.arc((740, 60, 1060, 380), start=15, end=330, fill=brand.color("mint"), width=3)
        for angle in range(0, 360, 30):
            radians = math.radians(angle)
            x = 900 + math.cos(radians) * 160
            y = 220 + math.sin(radians) * 160
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=brand.color("cream"))


def render_post(post: Post, brand: Brand, index: int = 0) -> Image.Image:
    dark = post.slot in {"morning", "evening"}
    background = brand.color("navy_deep") if dark else brand.color("cream")
    image = Image.new("RGB", (brand.width, brand.height), background)
    draw = ImageDraw.Draw(image)

    if post.slot == "morning":
        draw.ellipse((850, -120, 1210, 240), fill=brand.color("mint_strong"))
        draw.rounded_rectangle(
            (42, 128, 1038, 1180), radius=brand.tokens["corner_radius"], fill=brand.color("paper")
        )
        # Header and badge are redrawn on the light card below the brand line.
        draw.ellipse((64, 50, 112, 98), fill=brand.color("orange"))
        coin_font = load_font(brand.font_path, 28, 800)
        draw.text((76, 56), "₽", font=coin_font, fill=brand.color("navy"))
        brand_font = load_font(brand.font_path, 24, 800)
        draw.text((128, 60), brand.name, font=brand_font, fill=brand.color("cream"))
        _pill(draw, brand, post.card.badge, (80, 174), dark=False)
        title_bottom = _title(image, brand, post.card.title, 260, dark=False, width=900)
        subtitle_y = max(570, title_bottom + 32)
        _subtitle(image, brand, post.card.subtitle, subtitle_y, dark=False, width=850)
        if post.card.points:
            _points(image, brand, post, 720, dark=False)
        else:
            _wallet(image, brand, 665, 850)
        _footer(image, brand, post, dark=True)
        return image

    _header(image, brand, post, dark)
    if post.slot == "evening":
        _stars(image, brand, seed=index + 17, horoscope=post.is_horoscope)
        title_bottom = _title(image, brand, post.card.title, 275, dark=True, width=760)
        _subtitle(image, brand, post.card.subtitle, title_bottom + 36, dark=True, width=840)
        _points(image, brand, post, 730, dark=True)
        if not post.card.points:
            draw.arc((60, 810, 990, 1350), start=190, end=345, fill=brand.color("mint"), width=5)
            draw.ellipse((790, 870, 910, 990), fill=brand.color("orange"))
    else:
        draw.ellipse((850, 80, 1160, 390), fill=brand.color("mint"))
        title_bottom = _title(image, brand, post.card.title, 260, dark=False, width=900)
        _subtitle(image, brand, post.card.subtitle, title_bottom + 30, dark=False, width=900)
        _points(image, brand, post, 700, dark=False)
        if not post.card.points:
            _receipt(image, brand, 710, 800)
    _footer(image, brand, post, dark)
    return image


def render_avatar(brand: Brand) -> Image.Image:
    image = Image.new("RGB", (1024, 1024), brand.color("navy_deep"))
    draw = ImageDraw.Draw(image)
    draw.ellipse((80, 80, 944, 944), fill=brand.color("navy"))
    draw.ellipse((198, 198, 826, 826), fill=brand.color("mint"))
    draw.ellipse((292, 292, 732, 732), fill=brand.color("orange"))
    font = load_font(brand.font_path, 240, 800)
    text = "₽"
    box = draw.textbbox((0, 0), text, font=font)
    x = (1024 - (box[2] - box[0])) / 2
    y = (1024 - (box[3] - box[1])) / 2 - box[1] - 12
    draw.text((x, y), text, font=font, fill=brand.color("navy"))
    return image
