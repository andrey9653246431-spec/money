from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .brand import Brand
from .models import ContentError, load_posts
from .renderer import render_avatar, render_post


def build(args: argparse.Namespace) -> int:
    brand = Brand(args.root)
    posts = load_posts(args.input)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for index, post in enumerate(posts):
        try:
            image = render_post(post, brand, index)
        except ValueError as error:
            raise ContentError(f"{post.content_id}: {error}") from error
        filename = f"{index + 1:03d}_{post.slot}.png"
        path = output / filename
        image.save(path, format="PNG", optimize=True)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.append(
            {
                "content_id": post.content_id,
                "slot": post.slot,
                "rubric": post.rubric,
                "file": filename,
                "width": image.width,
                "height": image.height,
                "alt_text": post.alt_text,
                "image_prompt": post.image_prompt,
                "sha256": digest,
            }
        )
        print(f"OK {post.content_id}: {path}")
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Готово: {len(manifest)} карточек; manifest: {manifest_path}")
    return 0


def validate(args: argparse.Namespace) -> int:
    Brand(args.root)
    posts = load_posts(args.input)
    print(f"OK: {len(posts)} публикаций; данные, цвета и шрифт доступны")
    return 0


def avatar(args: argparse.Namespace) -> int:
    brand = Brand(args.root)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    render_avatar(brand).save(output, format="PNG", optimize=True)
    print(f"OK: {output}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="dbp-design", description="Дизайн-завод «Деньги без паники»"
    )
    root.add_argument(
        "--root", type=Path, default=None, help="Корень репозитория с brand/ и assets/"
    )
    commands = root.add_subparsers(dest="command", required=True)

    build_parser = commands.add_parser("build", help="Сгенерировать PNG и manifest.json")
    build_parser.add_argument("--input", "-i", type=Path, required=True, help="JSON с публикациями")
    build_parser.add_argument(
        "--out", "-o", type=Path, default=Path("dist"), help="Папка результата"
    )
    build_parser.set_defaults(func=build)

    validate_parser = commands.add_parser("validate", help="Проверить JSON и ресурсы")
    validate_parser.add_argument("--input", "-i", type=Path, required=True)
    validate_parser.set_defaults(func=validate)

    avatar_parser = commands.add_parser("avatar", help="Сгенерировать фирменный аватар 1024×1024")
    avatar_parser.add_argument("--out", "-o", type=Path, default=Path("dist/avatar.png"))
    avatar_parser.set_defaults(func=avatar)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except (ContentError, FileNotFoundError, OSError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
