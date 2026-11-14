from __future__ import annotations

import json
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from . import pharmacy, supplements
    from .config import Config
    from .edadil import EdadilProvider
    from .kuper import TOP10, KuperProvider, Offer
    from .mailer import send_email
    from .store import BasketStore, LastSearchStore, OffsetStore, basket_totals, grand_total
except ImportError:  # Direct execution: python price_bot/bot.py
    import pharmacy
    import supplements
    from config import Config
    from edadil import EdadilProvider
    from kuper import TOP10, KuperProvider, Offer
    from mailer import send_email
    from store import BasketStore, LastSearchStore, OffsetStore, basket_totals, grand_total


def fmt_money(value: float) -> str:
    return f"{value:.2f} ₽"


def short_name(name: str, limit: int = 60) -> str:
    name = " ".join(str(name).split())
    return name if len(name) <= limit else name[: limit - 1] + "…"


def main_menu() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🔍 Сравнить цены", "callback_data": "menu:search"}],
            [
                {"text": "🧺 Корзина", "callback_data": "menu:basket"},
                {"text": "📋 Список покупок", "callback_data": "menu:list"},
            ],
            [
                {"text": "🏪 Магазины", "callback_data": "menu:stores"},
                {"text": "❓ Помощь", "callback_data": "menu:help"},
            ],
        ]
    }


class TelegramAPI:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"

    def call(self, method: str, data: dict | None = None, timeout: int = 40) -> dict[str, Any]:
        body = json.dumps(data or {}, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.base}/{method}",
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            raise RuntimeError(
                f"Telegram {method}: {payload.get('description', f'HTTP {error.code}')}"
            ) from None
        except URLError as error:
            raise RuntimeError(f"Сеть Telegram {method}: {error.reason}") from None
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram {method}: {payload.get('description', 'ошибка')}")
        return payload.get("result") or {}

    def get_updates(self, offset: int | None, timeout: int = 30) -> list[dict]:
        data: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            data["offset"] = offset
        result = self.call("getUpdates", data, timeout=timeout + 15)
        return result if isinstance(result, list) else []

    def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> None:
        data: dict[str, Any] = {"chat_id": chat_id, "text": text[:4000]}
        if reply_markup:
            data["reply_markup"] = reply_markup
        self.call("sendMessage", data)

    def send_document(self, chat_id: int, filename: str, content: bytes, caption: str = "") -> None:
        boundary = "----money" + str(int(time.time() * 1000))
        parts = bytearray()
        parts.extend(
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
                f"{chat_id}\r\n"
            ).encode()
        )
        if caption:
            parts.extend(
                (
                    f"--{boundary}\r\n"
                    'Content-Disposition: form-data; name="caption"\r\n\r\n'
                    f"{caption}\r\n"
                ).encode()
            )
        parts.extend(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'
                "Content-Type: text/plain; charset=utf-8\r\n\r\n"
            ).encode()
        )
        parts.extend(content)
        parts.extend(f"\r\n--{boundary}--\r\n".encode())
        request = Request(
            f"{self.base}/sendDocument",
            data=bytes(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise RuntimeError(f"Telegram sendDocument: HTTP {error.code}") from None
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram sendDocument: {payload.get('description', 'ошибка')}")

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        try:
            self.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:200]})
        except RuntimeError:
            pass


class PriceBot:
    def __init__(self, config: Config):
        self.config = config
        self.api = TelegramAPI(config.bot_token)
        self.kuper = KuperProvider(config.lat, config.lon)
        self.edadil = EdadilProvider()
        state = config.state_dir
        self.baskets = BasketStore(state / "baskets.json")
        self.last_search = LastSearchStore(state / "last_search.json")
        self.offsets = OffsetStore(state / "offset.json")
        self.pharmacy_path = (
            Path(__file__).resolve().parent.parent / "data" / "pharmacy" / "prices.csv"
        )

    # ---------- команды ----------

    def cmd_start(self, chat_id: int) -> None:
        self.api.send_message(
            chat_id,
            "Привет! Я сравниваю цены в топ-10 супермаркетах РФ, собираю корзину "
            "и формирую список покупок.\n\n"
            "Нажмите «Сравнить цены» или просто напишите название товара.",
            main_menu(),
        )

    def cmd_help(self, chat_id: int) -> None:
        self.api.send_message(
            chat_id,
            "Команды:\n"
            "/search <товар> — сравнить цены\n"
            "/basket — корзина\n"
            "/list — список покупок\n"
            "/stores — доступные магазины\n"
            "/drug <название> — цены в аптеках (безрецептурные)\n"
            "/supp <название> — цены на БАДы в Купере\n"
            "/help — эта справка\n\n"
            "Цены берутся из Купера (живые цены и акции). Покрытие сетей зависит "
            "от точки доставки — бот честно показывает, какие магазины доступны.\n"
            "Едадил требует авторизации через Яндекс, поэтому его акции недоступны "
            "анонимно — вместо них показаны акции Купера.",
            main_menu(),
        )

    def cmd_stores(self, chat_id: int) -> None:
        try:
            stores = self.kuper.stores()
        except RuntimeError as error:
            self.api.send_message(chat_id, f"Не удалось получить список магазинов: {error}")
            return
        available = [s["name"] for s in stores]
        missing = [name for name in TOP10 if name not in available]
        text = "🏪 Магазины, доступные по точке доставки:\n"
        text += "\n".join(f"• {name}" for name in available) or "• нет данных"
        if missing:
            text += "\n\nНедоступны в этой точке: " + ", ".join(missing)
        self.api.send_message(chat_id, text, main_menu())

    def cmd_drug(self, chat_id: int, query: str) -> None:
        query = " ".join(query.split())[:100]
        if not query:
            self.api.send_message(
                chat_id, "Напишите название препарата, например: /drug парацетамол"
            )
            return
        offers = pharmacy.load_offers(self.pharmacy_path)
        if not offers:
            self.api.send_message(
                chat_id,
                "Прайс аптек пока не загружен. Цены появятся после обновления "
                "data/pharmacy/prices.csv.",
                main_menu(),
            )
            return
        found = pharmacy.search(offers, query)
        self.api.send_message(chat_id, pharmacy.format_results(query, found), main_menu())

    def cmd_supp(self, chat_id: int, query: str) -> None:
        query = " ".join(query.split())[:100]
        if not query:
            self.api.send_message(chat_id, "Напишите название БАДа, например: /supp омега-3")
            return
        self.api.send_message(chat_id, f"🔍 Ищу БАД «{query}» по магазинам…")
        try:
            offers = supplements.search_supplements(self.kuper, query)
        except Exception as error:  # сетевые сбои не должны ронять бота
            self.api.send_message(chat_id, f"Поиск БАДов временно недоступен: {error}")
            return
        self.api.send_message(chat_id, supplements.format_supplements(query, offers), main_menu())

    # ---------- поиск ----------

    def do_search(self, chat_id: int, user_id: int, query: str) -> None:
        query = " ".join(query.split())[:100]
        if not query:
            self.api.send_message(chat_id, "Напишите название товара, например: молоко")
            return
        self.api.send_message(chat_id, f"🔍 Ищу «{query}» по магазинам…")
        try:
            offers = self.kuper.search(query)
        except RuntimeError as error:
            self.api.send_message(chat_id, f"Поиск временно недоступен: {error}")
            return
        self.last_search.save(user_id, query, [o.to_dict() for o in offers])
        if not offers:
            self.api.send_message(
                chat_id,
                f"По «{query}» ничего не нашлось. Попробуйте другое название.",
                main_menu(),
            )
            return
        lines = [f"🔍 «{query}» — сравнение цен (Купер)", ""]
        buttons = []
        for index, offer in enumerate(offers[:8]):
            medal = "🏆 " if index == 0 else f"{index + 1}. "
            unit = f" · {fmt_money(offer.unit_price)}/{offer.unit}" if offer.unit_price else ""
            promo = f" · акция −{offer.discount_percent}%" if offer.discount_percent else ""
            lines.append(f"{medal}{offer.store} — {fmt_money(offer.price)}{unit}{promo}")
            lines.append(f"   {short_name(offer.name)}")
            lines.append("")
            buttons.append(
                [
                    {
                        "text": f"🧺 {offer.store} — {fmt_money(offer.price)}",
                        "callback_data": f"add:{index}",
                    }
                ]
            )
        try:
            total_stores = len(self.kuper.stores())
        except RuntimeError:
            total_stores = len(offers)
        lines.append(f"Доступно магазинов: {total_stores} из 10.")
        if not self.edadil.available():
            lines.append("Едадил недоступен без авторизации — показаны акции Купера.")
        buttons.append(
            [
                {"text": "🔍 Новый поиск", "callback_data": "menu:search"},
                {"text": "🧺 Корзина", "callback_data": "menu:basket"},
            ]
        )
        self.api.send_message(chat_id, "\n".join(lines), {"inline_keyboard": buttons})

    # ---------- корзина ----------

    def show_basket(self, chat_id: int, user_id: int) -> None:
        items = self.baskets.get(user_id)
        if not items:
            self.api.send_message(
                chat_id,
                "🧺 Корзина пуста. Найдите товар через «Сравнить цены» и добавьте кнопкой.",
                main_menu(),
            )
            return
        totals = basket_totals(items)
        lines = [
            f"🧺 Корзина — {len(items)} поз., {sum(int(i.get('qty', 1)) for i in items)} шт.",
            "",
        ]
        buttons = []
        for store, total in totals.items():
            lines.append(f"{store} — {fmt_money(total)}")
            for item in [i for i in items if i.get("store") == store]:
                qty = int(item.get("qty", 1))
                lines.append(
                    f"  {qty} × {short_name(str(item.get('name', '')), 45)} — "
                    f"{fmt_money(float(item.get('price') or 0) * qty)}"
                )
                sid = str(item.get("store_id", ""))
                sku = str(item.get("sku", ""))
                buttons.append(
                    [
                        {"text": "−", "callback_data": f"b:minus:{sid}:{sku}"},
                        {"text": f"{qty} шт", "callback_data": "menu:basket"},
                        {"text": "+", "callback_data": f"b:plus:{sid}:{sku}"},
                        {"text": "🗑", "callback_data": f"b:rm:{sid}:{sku}"},
                    ]
                )
            lines.append("")
        lines.append(f"Итого: {fmt_money(grand_total(items))}")
        buttons.append(
            [
                {"text": "🏆 Самый дешёвый вариант", "callback_data": "b:cheapest"},
                {"text": "📋 В список покупок", "callback_data": "menu:list"},
            ]
        )
        buttons.append([{"text": "🧹 Очистить корзину", "callback_data": "b:clear"}])
        self.api.send_message(chat_id, "\n".join(lines), {"inline_keyboard": buttons})

    def cheapest_basket(self, chat_id: int, user_id: int) -> None:
        items = self.baskets.get(user_id)
        if not items:
            self.api.send_message(chat_id, "Корзина пуста.")
            return
        self.api.send_message(chat_id, "🏆 Считаю самый дешёвый вариант… это займёт минуту.")
        per_store: dict[str, float] = {}
        complete: dict[str, bool] = {}
        for item in items:
            name = str(item.get("name", ""))
            qty = int(item.get("qty", 1))
            try:
                offers = self.kuper.search(name)
            except RuntimeError:
                offers = []
            found_stores = set()
            for offer in offers:
                per_store[offer.store] = per_store.get(offer.store, 0.0) + offer.price * qty
                found_stores.add(offer.store)
            for store in list(per_store):
                if store not in found_stores:
                    complete[store] = False
            for store in found_stores:
                complete.setdefault(store, True)
        if not per_store:
            self.api.send_message(chat_id, "Не удалось пересчитать корзину — попробуйте позже.")
            return
        ranked = sorted(per_store.items(), key=lambda kv: kv[1])
        lines = ["🏆 Суммы корзины по магазинам (пересчёт по текущим ценам):", ""]
        for store, total in ranked:
            mark = " ✅" if complete.get(store, True) else " (не всё есть)"
            lines.append(f"• {store} — {fmt_money(total)}{mark}")
        lines.append("")
        lines.append(f"Самый дешёвый: {ranked[0][0]} — {fmt_money(ranked[0][1])}")
        self.api.send_message(chat_id, "\n".join(lines), main_menu())

    # ---------- список покупок ----------

    def list_text(self, user_id: int) -> str:
        items = self.baskets.get(user_id)
        date = datetime.now().strftime("%d.%m.%Y")
        lines = [f"📋 Список покупок ({date})", ""]
        for index, item in enumerate(items, 1):
            qty = int(item.get("qty", 1))
            lines.append(
                f"{index}. {item.get('name', '')} — {item.get('store', '')}, "
                f"{fmt_money(float(item.get('price') or 0))} × {qty}"
            )
        lines.append("")
        lines.append(f"Итого: {fmt_money(grand_total(items))}")
        lines.append("")
        lines.append("Не переплачивай")
        return "\n".join(lines)

    def show_list(self, chat_id: int, user_id: int) -> None:
        items = self.baskets.get(user_id)
        if not items:
            self.api.send_message(
                chat_id,
                "Список пуст — сначала соберите корзину.",
                main_menu(),
            )
            return
        buttons = [
            [
                {"text": "📤 В чат", "callback_data": "l:send"},
                {"text": "📎 Файлом", "callback_data": "l:file"},
            ],
            [{"text": "✉️ На email", "callback_data": "l:email"}],
        ]
        self.api.send_message(chat_id, self.list_text(user_id), {"inline_keyboard": buttons})

    def send_list_email(self, chat_id: int, user_id: int) -> None:
        if not self.config.email_configured:
            self.api.send_message(
                chat_id,
                "✉️ Email пока не настроен: задайте SMTP_HOST, SMTP_USER, SMTP_PASS и SMTP_TO "
                "в Secrets репозитория (см. PRICE_BOT_SETUP.md).",
                main_menu(),
            )
            return
        text = self.list_text(user_id)
        try:
            ok = send_email(
                self.config,
                "Список покупок — Не переплачивай",
                text,
                filename="shopping_list.txt",
                content=text,
            )
        except Exception as error:
            self.api.send_message(chat_id, f"Не удалось отправить email: {error}")
            return
        self.api.send_message(
            chat_id,
            f"✉️ Список отправлен на {self.config.smtp_to}" if ok else "Email не отправлен.",
            main_menu(),
        )

    # ---------- обработка обновлений ----------

    def handle_message(self, message: dict) -> None:
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        user = message.get("from") or {}
        user_id = user.get("id")
        text = str(message.get("text") or "").strip()
        if not chat_id or not user_id or not text:
            return
        if text.startswith("/start"):
            self.cmd_start(chat_id)
        elif text.startswith("/help"):
            self.cmd_help(chat_id)
        elif text.startswith("/stores"):
            self.cmd_stores(chat_id)
        elif text.startswith("/basket"):
            self.show_basket(chat_id, user_id)
        elif text.startswith("/list"):
            self.show_list(chat_id, user_id)
        elif text.startswith("/supp"):
            self.cmd_supp(chat_id, text[len("/supp") :].strip())
        elif text.startswith("/drug"):
            self.cmd_drug(chat_id, text[len("/drug") :].strip())
        elif text.startswith("/search"):
            self.do_search(chat_id, user_id, text[len("/search") :].strip())
        elif text.startswith("/"):
            self.api.send_message(chat_id, "Неизвестная команда. /help — справка.", main_menu())
        else:
            self.do_search(chat_id, user_id, text)

    def handle_callback(self, query: dict) -> None:
        callback_id = str(query.get("id") or "")
        data = str(query.get("data") or "")
        message = query.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        user_id = (query.get("from") or {}).get("id")
        if not chat_id or not user_id:
            self.api.answer_callback(callback_id)
            return
        try:
            if data == "menu:search":
                self.api.send_message(chat_id, "Напишите название товара, например: молоко")
            elif data == "menu:basket":
                self.show_basket(chat_id, user_id)
            elif data == "menu:list":
                self.show_list(chat_id, user_id)
            elif data == "menu:stores":
                self.cmd_stores(chat_id)
            elif data == "menu:help":
                self.cmd_help(chat_id)
            elif data.startswith("add:"):
                self._callback_add(chat_id, user_id, data)
            elif data.startswith("b:"):
                self._callback_basket(chat_id, user_id, data)
            elif data == "l:send":
                self.api.send_message(chat_id, self.list_text(user_id), main_menu())
            elif data == "l:file":
                text = self.list_text(user_id)
                self.api.send_document(
                    chat_id, "shopping_list.txt", text.encode("utf-8"), "Список покупок"
                )
            elif data == "l:email":
                self.send_list_email(chat_id, user_id)
            else:
                self.api.answer_callback(callback_id, "Неизвестное действие")
                return
        except RuntimeError as error:
            self.api.send_message(chat_id, f"Ошибка: {error}")
        self.api.answer_callback(callback_id)

    def _callback_add(self, chat_id: int, user_id: int, data: str) -> None:
        try:
            index = int(data.split(":", 1)[1])
        except (IndexError, ValueError):
            self.api.send_message(chat_id, "Кнопка устарела — выполните поиск заново.")
            return
        entry = self.last_search.get(user_id)
        offers = (entry or {}).get("offers") or []
        if index < 0 or index >= len(offers):
            self.api.send_message(chat_id, "Кнопка устарела — выполните поиск заново.")
            return
        offer = Offer.from_dict(offers[index])
        item = {
            "store": offer.store,
            "store_id": offer.store_id,
            "name": offer.name,
            "price": offer.price,
            "unit_price": offer.unit_price,
            "unit": offer.unit,
            "qty": 1,
            "sku": offer.sku,
        }
        self.baskets.add(user_id, item)
        self.api.send_message(
            chat_id,
            f"🧺 Добавлено: {short_name(offer.name, 45)} — {offer.store}, {fmt_money(offer.price)}",
            {
                "inline_keyboard": [
                    [
                        {"text": "🧺 Корзина", "callback_data": "menu:basket"},
                        {"text": "🔍 Новый поиск", "callback_data": "menu:search"},
                    ]
                ]
            },
        )

    def _callback_basket(self, chat_id: int, user_id: int, data: str) -> None:
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        if action == "clear":
            self.baskets.clear(user_id)
            self.api.send_message(chat_id, "🧹 Корзина очищена.", main_menu())
            return
        if action == "cheapest":
            self.cheapest_basket(chat_id, user_id)
            return
        if action in {"plus", "minus", "rm"} and len(parts) >= 4:
            store_id, sku = parts[2], parts[3]
            items = self.baskets.get(user_id)
            current = next(
                (
                    int(i.get("qty", 1))
                    for i in items
                    if str(i.get("store_id")) == store_id and str(i.get("sku")) == sku
                ),
                0,
            )
            if action == "plus":
                self.baskets.set_qty(user_id, store_id, sku, current + 1)
            elif action == "minus":
                self.baskets.set_qty(user_id, store_id, sku, current - 1)
            else:
                self.baskets.remove(user_id, store_id, sku)
            self.show_basket(chat_id, user_id)
            return
        self.api.send_message(chat_id, "Неизвестное действие.", main_menu())

    def handle_update(self, update: dict) -> None:
        if "message" in update:
            self.handle_message(update["message"])
        elif "callback_query" in update:
            self.handle_callback(update["callback_query"])

    # ---------- цикл ----------

    def run(self) -> int:
        if not self.config.bot_token:
            print("ERROR: нет PRICE_BOT_TOKEN")
            return 2
        deadline = time.monotonic() + max(1, self.config.session_minutes) * 60
        offset = self.offsets.get()

        # Отменённый workflow присылает SIGTERM: выходим из цикла штатно,
        # чтобы offset успел лечь в state/bot/ и апдейты не обработались дважды.
        stop = {"requested": False}

        def _request_stop(signum: int, _frame: object) -> None:
            stop["requested"] = True
            print(f"Сигнал {signum}: завершаю сессию после текущего апдейта")

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, _request_stop)
            except ValueError:
                # Не главный поток (например, в тестах) — обходимся без сигналов.
                pass

        print(f"Бот запущен на {self.config.session_minutes} мин.; offset={offset}")
        while time.monotonic() < deadline and not stop["requested"]:
            try:
                updates = self.api.get_updates(offset, timeout=self.config.poll_timeout)
            except RuntimeError as error:
                print(f"WARN: {error}")
                time.sleep(5)
                continue
            for update in updates:
                try:
                    self.handle_update(update)
                except Exception as error:  # не роняем сессию из-за одного апдейта
                    print(f"WARN: обработка апдейта: {error}")
                offset = int(update.get("update_id", offset or 0)) + 1
            if updates:
                self.offsets.set(offset)
        print("Сессия завершена, offset сохранён")
        return 0


def main() -> int:
    config = Config()
    bot = PriceBot(config)
    return bot.run()


if __name__ == "__main__":
    raise SystemExit(main())
