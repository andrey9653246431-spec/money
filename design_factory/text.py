from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageDraw, ImageFont


@dataclass(frozen=True)
class TextLayout:
    lines: list[str]
    font: ImageFont.FreeTypeFont
    size: int
    line_height: int
    spacing: int

    @property
    def height(self) -> int:
        return len(self.lines) * self.line_height + max(0, len(self.lines) - 1) * self.spacing


def load_font(path: str | Path, size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(path), size=size)
    try:
        font.set_variation_by_axes([weight])
    except (AttributeError, OSError, ValueError):
        # Static fonts and Pillow builds without variable-font support still render.
        pass
    return font


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str | Path,
    *,
    max_size: int,
    min_size: int,
    max_width: int,
    max_height: int,
    max_lines: int,
    weight: int = 400,
) -> TextLayout:
    for size in range(max_size, min_size - 1, -2):
        font = load_font(font_path, size, weight)
        lines = wrap_text(draw, text, font, max_width)
        spacing = max(8, round(size * 0.24))
        line_height = round(size * 1.12)
        height = len(lines) * line_height + max(0, len(lines) - 1) * spacing
        if len(lines) <= max_lines and height <= max_height:
            return TextLayout(lines, font, size, line_height, spacing)
    raise ValueError(f"Текст не помещается в карточку: {text[:100]!r}")


def draw_layout(
    draw: ImageDraw.ImageDraw,
    layout: TextLayout,
    xy: tuple[int, int],
    fill: str,
) -> int:
    x, y = xy
    for line in layout.lines:
        draw.text((x, y), line, font=layout.font, fill=fill)
        y += layout.line_height + layout.spacing
    return y
