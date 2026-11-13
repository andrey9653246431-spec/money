from __future__ import annotations

import argparse
import json
from pathlib import Path

import scripts.publish_max as max_module
from scripts.publish_max import (
    chunk_text,
    full_text,
    image_payload_from_upload_response,
    publish,
    state_path,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "content" / "examples" / "approved-example.json"


def _image_dir(tmp_path: Path, payload: dict) -> Path:
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    manifest = []
    for post in payload["posts"]:
        filename = f"{post['slot']}.png"
        (image_dir / filename).write_bytes(b"not-sent-in-dry-run")
        manifest.append({"content_id": post["content_id"], "file": filename})
    (image_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return image_dir


def test_max_text_uses_max_text_and_footer() -> None:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    post = payload["posts"][0]
    text = full_text(post, footer="Не переплачивай")
    assert text.startswith(post["max_text"])
    assert "#деньги" in text
    assert text.endswith("Не переплачивай")
    assert text.count("Не переплачивай") == 1


def test_footer_not_duplicated() -> None:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    post = dict(payload["posts"][0])
    post["max_text"] = post["max_text"] + "\n\nНе переплачивай"
    text = full_text(post, footer="Не переплачивай")
    assert text.count("Не переплачивай") == 1


def test_image_payload_prefers_photos() -> None:
    response = {"photos": {"photoIds": {"token": "abc"}}}
    assert image_payload_from_upload_response(response) == {
        "photos": {"photoIds": {"token": "abc"}}
    }
    assert image_payload_from_upload_response({"token": "xyz"}) == {"token": "xyz"}


def test_chunking_respects_limit() -> None:
    long_text = "\n\n".join(f"Абзац {index} " + "текст " * 200 for index in range(10))
    chunks = chunk_text(long_text, limit=1000)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert "Абзац 0" in "".join(chunks)
    assert "Абзац 9" in "".join(chunks)


def test_dry_run_needs_no_max_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MAX_BOT_TOKEN", raising=False)
    monkeypatch.delenv("MAX_CHAT_ID", raising=False)
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    args = argparse.Namespace(
        content=EXAMPLE,
        slot="morning",
        image_dir=_image_dir(tmp_path, payload),
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


def test_retry_does_not_duplicate_post(tmp_path: Path, monkeypatch) -> None:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    class FakeClient:
        def __init__(self) -> None:
            self.uploads = 0
            self.messages: list[tuple[str, list]] = []

        def upload_image(self, path: Path) -> dict:
            self.uploads += 1
            return {"photos": {"photoIds": {"token": "tok"}}}

        def send_message(self, text: str, attachments=None) -> str:
            self.messages.append((text, attachments or []))
            return f"mid-{len(self.messages)}"

    client = FakeClient()
    monkeypatch.setattr(max_module, "MaxClient", lambda token, chat_id: client)
    monkeypatch.setenv("MAX_BOT_TOKEN", "test-token")
    monkeypatch.setenv("MAX_CHAT_ID", "-123456789")
    args = argparse.Namespace(
        content=EXAMPLE,
        slot="morning",
        image_dir=_image_dir(tmp_path, payload),
        state_dir=tmp_path / "state",
        archive_dir=tmp_path / "archive",
        dry_run=False,
    )
    assert publish(args) == 0
    assert publish(args) == 0
    assert client.uploads == 1
    assert len(client.messages) == 1
    text, attachments = client.messages[0]
    assert text.endswith("Не переплачивай")
    assert attachments == [{"type": "image", "payload": {"photos": {"photoIds": {"token": "tok"}}}}]
    assert len(list((tmp_path / "state").glob("*.json"))) == 1
    assert (tmp_path / "archive" / "2026-11-12_morning.json").exists()
