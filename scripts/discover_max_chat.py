from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://platform-api2.max.ru"
WANTED_TYPES = ("bot_added", "bot_started", "message_created")


def fetch_updates(token: str, marker: int | None, timeout: int) -> dict:
    params: dict[str, str] = {"limit": "100", "timeout": str(timeout)}
    if marker is not None:
        params["marker"] = str(marker)
    params["types"] = ",".join(WANTED_TYPES)
    url = API_BASE + "/updates?" + urlencode(params)
    request = Request(url, headers={"Authorization": token}, method="GET")
    try:
        with urlopen(request, timeout=timeout + 15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        code = payload.get("code", f"HTTP {error.code}")
        raise RuntimeError(f"MAX GET /updates: {code}") from None
    except URLError as error:
        hint = ""
        if "CERTIFICATE_VERIFY_FAILED" in str(error.reason):
            hint = (
                "; установите корневой сертификат Минцифры "
                "(Russian Trusted CA) в доверенное хранилище"
            )
        raise RuntimeError(f"Сеть MAX GET /updates: {error.reason}{hint}") from None


def extract_chat_ids(updates: list[dict]) -> list[tuple[int, str, bool]]:
    found: list[tuple[int, str, bool]] = []
    for update in updates:
        if not isinstance(update, dict):
            continue
        update_type = str(update.get("update_type", ""))
        chat_id = update.get("chat_id")
        if chat_id is None and isinstance(update.get("message"), dict):
            recipient = update["message"].get("recipient") or {}
            chat_id = recipient.get("chat_id")
        if chat_id is None:
            continue
        try:
            chat_id_int = int(chat_id)
        except (TypeError, ValueError):
            continue
        is_channel = bool(update.get("is_channel"))
        if update_type in ("bot_added", "bot_started"):
            found.append((chat_id_int, update_type, is_channel))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Разовая проверка: получить chat_id канала MAX через Long Polling."
    )
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--poll-timeout", type=int, default=30)
    args = parser.parse_args()

    token = os.environ.get("MAX_BOT_TOKEN", "").strip()
    if not token:
        print("ERROR: нет MAX_BOT_TOKEN", file=sys.stderr)
        return 2

    deadline = time.monotonic() + max(10, args.timeout_seconds)
    marker: int | None = None
    seen: set[int] = set()
    print("Жду событие bot_added/bot_started. Добавьте бота в канал MAX как администратора.")
    while time.monotonic() < deadline:
        try:
            result = fetch_updates(token, marker, args.poll_timeout)
        except RuntimeError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        marker = result.get("marker")
        for chat_id, update_type, is_channel in extract_chat_ids(result.get("updates", [])):
            if chat_id in seen:
                continue
            seen.add(chat_id)
            kind = "канал" if is_channel else "чат/диалог"
            print(f"FOUND: chat_id={chat_id}; type={update_type}; kind={kind}")
            print(f"MAX_CHAT_ID={chat_id}")
            if is_channel:
                print("Это канал. Сохраните MAX_CHAT_ID в Secrets репозитория.")
                return 0
        time.sleep(1)

    print("ERROR: за отведённое время событие не пришло.", file=sys.stderr)
    print(
        "Проверьте: бот добавлен в канал как администратор; Webhook-подписка не активна.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
