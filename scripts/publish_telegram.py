from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from .validate_content import content_id, validate_payload
except ImportError:  # Direct execution: python scripts/publish_telegram.py
    from validate_content import content_id, validate_payload


CHANNEL_URL = "https://t.me/ne_perepl"
BOT_URL = "https://t.me/ne_perepl_bot"
CHANNEL_FOOTER = "Не переплачивай @ne_perepl\n🤖 Бот сравнения цен: @ne_perepl_bot"


def as_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().casefold() in {"1", "true", "yes", "да"}


def full_text(post: dict) -> str:
    text = str(post["telegram_text"]).strip()
    tags = [str(tag).strip().lstrip("#") for tag in post.get("hashtags", []) if str(tag).strip()]
    sources = [str(url).strip() for url in post.get("source_urls", []) if str(url).strip()]
    if tags:
        text += "\n\n" + " ".join("#" + tag for tag in dict.fromkeys(tags))
    if sources:
        text += "\n\nИсточники:\n" + "\n".join(sources)
    if "Не переплачивай @ne_perepl" not in text:
        text += "\n\n" + CHANNEL_FOOTER
    return text


def chunk_text(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return chunks


class TelegramClient:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    def _request(self, method: str, body: bytes, content_type: str) -> dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        for attempt in range(3):
            request = Request(url, data=body, headers={"Content-Type": content_type}, method="POST")
            try:
                with urlopen(request, timeout=45) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not payload.get("ok"):
                    raise RuntimeError(
                        f"Telegram отклонил {method}: {payload.get('description', 'ошибка')}"
                    )
                return payload["result"]
            except HTTPError as error:
                raw = error.read().decode("utf-8", errors="replace")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {}
                description = payload.get("description", f"HTTP {error.code}")
                retry_after = (payload.get("parameters") or {}).get("retry_after")
                if error.code == 429 and attempt < 2:
                    time.sleep(int(retry_after or 3))
                    continue
                if error.code >= 500 and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(f"Telegram {method}: {description}") from None
            except URLError as error:
                if attempt >= 2:
                    raise RuntimeError(f"Сеть Telegram {method}: {error.reason}") from None
                time.sleep(2**attempt)
        raise RuntimeError(f"Не удалось вызвать Telegram {method}")

    def _json(self, method: str, data: dict) -> dict[str, Any]:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return self._request(method, body, "application/json; charset=utf-8")

    def send_message(self, text: str) -> int:
        result = self._json("sendMessage", {"chat_id": self.chat_id, "text": text})
        return int(result["message_id"])

    def send_photo(self, path: Path, caption: str) -> int:
        boundary = "----money" + uuid.uuid4().hex
        parts = bytearray()

        def field(name: str, value: str) -> None:
            header = (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
            )
            parts.extend(header.encode())

        field("chat_id", self.chat_id)
        if caption:
            field("caption", caption)
        filename = path.name
        mime = mimetypes.guess_type(filename)[0] or "image/png"
        photo_header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        )
        parts.extend(photo_header.encode())
        parts.extend(path.read_bytes())
        parts.extend(f"\r\n--{boundary}--\r\n".encode())
        result = self._request(
            "sendPhoto", bytes(parts), f"multipart/form-data; boundary={boundary}"
        )
        return int(result["message_id"])


def state_path(directory: Path, cid: str) -> Path:
    digest = hashlib.sha256(cid.encode("utf-8")).hexdigest()[:20]
    return directory / f"{digest}.json"


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def publish(args: argparse.Namespace) -> int:
    payload = json.loads(args.content.read_text(encoding="utf-8"))
    errors, warnings = validate_payload(payload, args.slot, require_approved=True)
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        raise RuntimeError("Контент не прошёл проверку: " + "; ".join(errors))
    index, post = next((i, p) for i, p in enumerate(payload["posts"]) if p["slot"] == args.slot)
    cid = content_id(post, payload["date"], index)
    manifest = json.loads((args.image_dir / "manifest.json").read_text(encoding="utf-8"))
    image_entry = next((entry for entry in manifest if entry["content_id"] == cid), None)
    if image_entry is None:
        raise RuntimeError(f"В manifest нет изображения для {cid}")
    image = args.image_dir / image_entry["file"]
    text = full_text(post)
    if args.dry_run:
        chunks_count = len(chunk_text(text))
        print(
            f"DRY RUN: {cid}; slot={args.slot}; image={image}; "
            f"знаков={len(text)}; частей={chunks_count}"
        )
        print("Telegram API не вызывался; state не изменён")
        return 0

    import os

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Нет TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID")
    # The same content may intentionally go to a test and later to a production channel.
    state_file = state_path(args.state_dir, f"{chat_id}:{cid}")
    state = (
        json.loads(state_file.read_text(encoding="utf-8"))
        if state_file.exists()
        else {"content_id": cid, "text_message_ids": []}
    )
    if state.get("status") == "published":
        print(f"SKIP: {cid} уже опубликован; message_id={state.get('photo_message_id')}")
        return 0
    client = TelegramClient(token, chat_id)
    if len(text) <= 1000:
        message_id = client.send_photo(image, text)
        state.update(status="published", photo_message_id=message_id, text_message_ids=[])
        save_state(state_file, state)
    else:
        if not state.get("photo_message_id"):
            caption = str(post.get("working_title") or "Деньги без паники")[:900]
            state["photo_message_id"] = client.send_photo(image, caption)
            state["status"] = "photo_sent"
            save_state(state_file, state)
        chunks = chunk_text(text)
        sent = list(state.get("text_message_ids", []))
        for chunk in chunks[len(sent) :]:
            sent.append(client.send_message(chunk))
            state["text_message_ids"] = sent
            save_state(state_file, state)
        state["status"] = "published"
        save_state(state_file, state)
    state["published_at"] = datetime.now(UTC).isoformat()
    save_state(state_file, state)
    args.archive_dir.mkdir(parents=True, exist_ok=True)
    archive = args.archive_dir / f"{payload['date']}_{args.slot}.json"
    if not archive.exists():
        shutil.copy2(args.content, archive)
    print(f"OK: {cid}; photo={state['photo_message_id']}; text={state.get('text_message_ids', [])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--slot", choices=["morning", "day", "evening", "promo"], required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--dry-run", type=as_bool, default=True)
    args = parser.parse_args()
    try:
        return publish(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
