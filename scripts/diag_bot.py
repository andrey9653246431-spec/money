"""Диагностика бота сравнения цен: токен, Купер, скорость поиска.

Запуск:
    python scripts/diag_bot.py

Печатает только безопасные данные: username/id бота (без токена), список
магазинов и время ответа. Секреты в вывод не попадают.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from price_bot.config import Config  # noqa: E402
from price_bot.kuper import KuperProvider  # noqa: E402


def main() -> int:
    config = Config()
    problems = 0

    print("=== 1. Конфигурация ===")
    print(f"BOT_LAT/BOT_LON: {config.lat}, {config.lon}")
    print(f"BOT_SESSION_MINUTES: {config.session_minutes}")
    print(f"SMTP настроен: {config.email_configured}")
    if not config.bot_token:
        print("❌ Нет PRICE_BOT_TOKEN и нет TELEGRAM_BOT_TOKEN")
        return 1
    source = "PRICE_BOT_TOKEN" if os.environ.get("PRICE_BOT_TOKEN") else "TELEGRAM_BOT_TOKEN"
    print(f"Токен взят из: {source} (значение не печатается)")

    print()
    print("=== 2. Telegram: кто этот бот ===")
    from price_bot.bot import TelegramAPI

    api = TelegramAPI(config.bot_token)
    try:
        me = api.call("getMe", {})
        print(f"✅ Бот: @{me.get('username', '?')} (id={me.get('id', '?')})")
        print("   Сверьте username с тем ботом, которому вы пишете в Telegram.")
    except RuntimeError as error:
        problems += 1
        print(f"❌ getMe: {error}")
        print("   Токен недействителен или Telegram недоступен из этой сети.")
        return 1

    print()
    print("=== 3. Telegram: есть ли вебхук (он блокирует getUpdates) ===")
    try:
        info = api.call("getWebhookInfo", {})
        url = info.get("url") or ""
        pending = info.get("pending_update_count", 0)
        print(f"webhook url: {url or '(пусто — это правильно)'}")
        print(f"в очереди обновлений: {pending}")
        if url:
            problems += 1
            print("❌ Вебхук установлен — getUpdates вернёт 409 Conflict, бот не ответит.")
            print("   Удалите: https://api.telegram.org/bot<ТОКЕН>/deleteWebhook")
        if pending > 0:
            print(f"ℹ В очереди {pending} обновлений — значит боту писали, но он их не забрал.")
    except RuntimeError as error:
        problems += 1
        print(f"❌ getWebhookInfo: {error}")

    print()
    print("=== 4. Купер: магазины ===")
    kuper = KuperProvider(config.lat, config.lon)
    started = time.monotonic()
    try:
        stores = kuper.stores()
        elapsed = time.monotonic() - started
        print(f"✅ Магазинов: {len(stores)} из 10 за {elapsed:.1f} с")
        print("   " + ", ".join(store["name"] for store in stores))
    except Exception as error:
        problems += 1
        print(f"❌ Магазины: {type(error).__name__}: {error}")
        traceback.print_exc()
        return 1

    print()
    print("=== 5. Купер: поиск «молоко» ===")
    started = time.monotonic()
    try:
        offers = kuper.search("молоко")
        elapsed = time.monotonic() - started
        print(f"✅ Предложений: {len(offers)} за {elapsed:.1f} с")
        for offer in offers[:3]:
            print(f"   {offer.store}: {offer.price:.2f} ₽ — {offer.name[:50]}")
    except Exception as error:
        problems += 1
        print(f"❌ Поиск: {type(error).__name__}: {error}")
        traceback.print_exc()

    print()
    print("=== Итог ===")
    if problems == 0:
        print("✅ Все проверки пройдены: бот и Купер доступны из этой сети.")
        print("   Если в Telegram всё равно нет ответа — смотрите шаг UPDATE в логах сессии:")
        print("   приходят ли сообщения вообще и что бот на них отвечает.")
    else:
        print(f"❌ Проблем: {problems}. Подробности выше.")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
