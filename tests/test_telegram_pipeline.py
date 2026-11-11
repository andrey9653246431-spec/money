from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts.publish_telegram as telegram_module
from design_factory.brand import Brand
from design_factory.models import load_posts
from design_factory.renderer import render_post
from scripts.publish_telegram import CHANNEL_FOOTER, chunk_text, full_text, publish, state_path
from scripts.validate_content import validate_payload

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "content" / "examples" / "approved-example.json"


def test_approved_example_passes_validation() -> None:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    errors, warnings = validate_payload(payload, None, require_approved=True)
    assert errors == []
    assert isinstance(warnings, list)


def test_approved_example_renders() -> None:
    posts = load_posts(EXAMPLE)
    brand = Brand(ROOT)
    assert len(posts) == 3
    for index, post in enumerate(posts):
        assert render_post(post, brand, index).size == (1080, 1350)


def test_text_and_chunks() -> None:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    text = full_text(payload["posts"][0])
    assert "#деньги" in text
    assert "Источники" not in text
    assert text.endswith(CHANNEL_FOOTER)
    assert text.count("https://t.me/ne_perepl") == 1
    long_text = "\n\n".join(f"Абзац {index} " + "текст " * 200 for index in range(10))
    chunks = chunk_text(long_text, limit=1000)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)
    for word in ("Абзац 0", "Абзац 9"):
        assert word in "".join(chunks)


def test_dry_run_needs_no_telegram_secrets(tmp_path: Path) -> None:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    manifest = []
    for post in payload["posts"]:
        filename = f"{post['slot']}.png"
        (image_dir / filename).write_bytes(b"not-sent-in-dry-run")
        manifest.append({"content_id": post["content_id"], "file": filename})
    (image_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    args = argparse.Namespace(
        content=EXAMPLE,
        slot="morning",
        image_dir=image_dir,
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        dry_run=True,
    )
    assert publish(args) == 0
    assert not (tmp_path / "state").exists()
    assert not (tmp_path / "archive").exists()


def test_state_filename_is_safe(tmp_path: Path) -> None:
    path = state_path(tmp_path, "../../secret")
    assert path.parent == tmp_path
    assert "secret" not in path.name


def test_retry_does_not_duplicate_long_post(tmp_path: Path, monkeypatch) -> None:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    manifest = []
    for post in payload["posts"]:
        filename = f"{post['slot']}.png"
        (image_dir / filename).write_bytes(b"fake-png")
        manifest.append({"content_id": post["content_id"], "file": filename})
    (image_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    class FakeClient:
        def __init__(self) -> None:
            self.photos: list[str] = []
            self.messages: list[str] = []

        def send_photo(self, path: Path, caption: str) -> int:
            self.photos.append(caption)
            return 555

        def send_message(self, text: str) -> int:
            self.messages.append(text)
            return 1000 + len(self.messages)

    client = FakeClient()
    monkeypatch.setattr(telegram_module, "TelegramClient", lambda token, chat_id: client)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@test_channel")
    args = argparse.Namespace(
        content=EXAMPLE,
        slot="day",
        image_dir=image_dir,
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        dry_run=False,
    )
    assert publish(args) == 0
    assert publish(args) == 0
    assert len(client.photos) == 1
    assert len(client.messages) == 1
    assert client.messages[0].endswith(CHANNEL_FOOTER)
    assert client.photos[0] == payload["posts"][1]["working_title"]
    assert len(list((tmp_path / "state").glob("*.json"))) == 1
    assert (tmp_path / "archive" / "2026-11-12_day.json").exists()
