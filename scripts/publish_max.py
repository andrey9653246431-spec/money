from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from .validate_content import content_id, validate_payload
except ImportError:  # Direct execution: python scripts/publish_max.py
    from validate_content import content_id, validate_payload


API_BASE = "https://platform-api2.max.ru"
MAX_TEXT_LIMIT = 4000
CHUNK_LIMIT = 3900
DEFAULT_FOOTER = "Не переплачивай"


def as_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().casefold() in {"1", "true", "yes", "да"}


def channel_footer() -> str:
    channel_url = os.environ.get("MAX_CHANNEL_URL", "").strip()
    if channel_url:
        return f"{DEFAULT_FOOTER}\n{channel_url}"
    return DEFAULT_FOOTER


def full_text(post: dict, footer: str | None = None) -> str:
    text = str(post.get("max_text") or post.get("telegram_text") or "").strip()
    tags = [str(tag).strip().lstrip("#") for tag in post.get("hashtags", []) if str(tag).strip()]
    sources = [str(url).strip() for url in post.get("source_urls", []) if str(url).strip()]
    if tags:
        text += "\n\n" + " ".join("#" + tag for tag in dict.fromkeys(tags))
    if sources:
        text += "\n\nИсточники:\n" + "\n".join(sources)
    tail = footer if footer is not None else channel_footer()
    if tail and tail not in text:
        text += "\n\n" + tail
    return text


def chunk_text(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
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


def image_payload_from_upload_response(response: dict[str, Any]) -> dict[str, Any]:
    """Собирает payload вложения image из ответа загрузки.

    Свежая загрузка изображения возвращает {"photos": {...}} — его нужно
    передавать как есть (см. официальные библиотеки MAX). Если сервер вернул
    готовый token, используем его.
    """
    photos = response.get("photos")
    if isinstance(photos, dict) and photos:
        return {"photos": photos}
    token = response.get("token")
    if isinstance(token, str) and token:
        return {"token": token}
    raise RuntimeError("MAX не вернул токен изображения после загрузки")


class MaxClient:
    def __init__(self, token: str, chat_id: int):
        self.token = token
        self.chat_id = chat_id

    def _request(
        self,
        method: str,
        url: str,
        body: bytes | None,
        headers: dict[str, str],
        *,
        retry_not_ready: bool = False,
    ) -> dict[str, Any]:
        attempts = 6 if retry_not_ready else 3
        for attempt in range(attempts):
            request = Request(url, data=body, headers=headers, method=method)
            try:
                with urlopen(request, timeout=60) as response:
                    raw = response.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
            except HTTPError as error:
                raw = error.read().decode("utf-8", errors="replace")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {}
                code = str(payload.get("code", ""))
                message = str(payload.get("message", f"HTTP {error.code}"))
                if code == "attachment.not.ready" and attempt < attempts - 1:
                    time.sleep(2**attempt)
                    continue
                if error.code == 429 and attempt < attempts - 1:
                    time.sleep(3)
                    continue
                if error.code >= 500 and attempt < attempts - 1:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(f"MAX {method} {url.split('?')[0]}: {code or message}") from None
            except URLError as error:
                if attempt >= attempts - 1:
                    hint = ""
                    if "CERTIFICATE_VERIFY_FAILED" in str(error.reason):
                        hint = (
                            "; установите корневой сертификат Минцифры "
                            "(Russian Trusted CA) в доверенное хранилище"
                        )
                    raise RuntimeError(f"Сеть MAX {method}: {error.reason}{hint}") from None
                time.sleep(2**attempt)
        raise RuntimeError(f"Не удалось вызвать MAX {method}")

    def _json(
        self, method: str, path: str, data: dict | None, *, retry_not_ready: bool = False
    ) -> dict[str, Any]:
        url = API_BASE + path
        body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
        headers = {"Authorization": self.token}
        if body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        return self._request(method, url, body, headers, retry_not_ready=retry_not_ready)

    def get_upload_url(self) -> str:
        result = self._json("POST", "/uploads?type=image", None)
        url = result.get("url")
        if not isinstance(url, str) or not url:
            raise RuntimeError("MAX не вернул URL загрузки изображения")
        return url

    def upload_image(self, path: Path) -> dict[str, Any]:
        upload_url = self.get_upload_url()
        boundary = "----money" + uuid.uuid4().hex
        filename = path.name
        mime = mimetypes.guess_type(filename)[0] or "image/png"
        parts = bytearray()
        parts.extend(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="data"; filename="{filename}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode()
        )
        parts.extend(path.read_bytes())
        parts.extend(f"\r\n--{boundary}--\r\n".encode())
        result = self._request(
            "POST",
            upload_url,
            bytes(parts),
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        return image_payload_from_upload_response(result)

    def send_message(self, text: str, attachments: list[dict[str, Any]] | None = None) -> str:
        query = urlencode({"chat_id": self.chat_id})
        body: dict[str, Any] = {"text": text, "notify": True}
        if attachments:
            body["attachments"] = attachments
        result = self._json("POST", f"/messages?{query}", body, retry_not_ready=True)
        message = result.get("message") or {}
        body_obj = message.get("body") or {}
        mid = body_obj.get("mid")
        if not isinstance(mid, str) or not mid:
            raise RuntimeError("MAX не вернул mid созданного сообщения")
        return mid


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
        print("MAX API не вызывался; state не изменён")
        return 0

    token = os.environ.get("MAX_BOT_TOKEN", "").strip()
    chat_id_raw = os.environ.get("MAX_CHAT_ID", "").strip()
    if not token or not chat_id_raw:
        raise RuntimeError("Нет MAX_BOT_TOKEN или MAX_CHAT_ID")
    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        raise RuntimeError("MAX_CHAT_ID должен быть целым числом") from None
    # Тот же контент может идти в тестовый и позже в продакшн-канал.
    state_file = state_path(args.state_dir, f"{chat_id}:{cid}")
    state = (
        json.loads(state_file.read_text(encoding="utf-8"))
        if state_file.exists()
        else {"content_id": cid, "text_message_ids": []}
    )
    if state.get("status") == "published":
        print(f"SKIP: {cid} уже опубликован в MAX; message_id={state.get('message_id')}")
        return 0
    client = MaxClient(token, chat_id)
    if len(text) <= MAX_TEXT_LIMIT:
        image_payload = client.upload_image(image)
        mid = client.send_message(text, [{"type": "image", "payload": image_payload}])
        state.update(status="published", message_id=mid, text_message_ids=[])
        save_state(state_file, state)
    else:
        if not state.get("message_id"):
            image_payload = client.upload_image(image)
            caption = str(post.get("working_title") or "Деньги без паники")[:900]
            state["message_id"] = client.send_message(
                caption, [{"type": "image", "payload": image_payload}]
            )
            state["status"] = "photo_sent"
            save_state(state_file, state)
        chunks = chunk_text(text)
        sent = list(state.get("text_message_ids", []))
        for chunk in chunks[len(sent) :]:
            sent.append(client.send_message(chunk))
            state["text_message_ids"] = sent
            save_state(state_file, state)
            time.sleep(0.6)
        state["status"] = "published"
        save_state(state_file, state)
    state["published_at"] = datetime.now(UTC).isoformat()
    save_state(state_file, state)
    args.archive_dir.mkdir(parents=True, exist_ok=True)
    archive = args.archive_dir / f"{payload['date']}_{args.slot}.json"
    if not archive.exists():
        shutil.copy2(args.content, archive)
    print(f"OK: {cid}; message={state['message_id']}; text={state.get('text_message_ids', [])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--slot", choices=["morning", "day", "evening"], required=True)
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
