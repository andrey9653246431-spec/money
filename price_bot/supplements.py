"""Поиск БАДов (пищевых добавок) по магазинам Купера.

Купер отдаёт нечёткую выдачу: по «БАД» приходит пиво, поэтому здесь каждый
товар проверяется по словам запроса. БАД — не лекарство, эту оговорку бот
показывает в каждом ответе.
"""

from __future__ import annotations

import json
import time

from .kuper import BASE, HEADERS, KuperProvider, Offer, normalize_product

DISCLAIMER = (
    "БАД — это пищевая добавка, а не лекарство. Она не заменяет лечение и не "
    "является медицинской рекомендацией. Перед приёмом проконсультируйтесь с врачом."
)


PET_MARKERS = ("собак", "кошк", "кот", "питомц", "корм", "лакомств", "для животн", "щенк")


def is_pet_product(product: dict) -> bool:
    name = str(product.get("name") or "").casefold()
    return any(marker in name for marker in PET_MARKERS)


def _stem(word: str) -> str:
    """Грубая основа слова: «витамины» и «витамин» дают одинаковый корень."""
    return word[:5] if len(word) > 5 else word


def query_words(query: str) -> list[str]:
    return [w for w in query.casefold().replace(",", " ").split() if len(w) >= 2]


def is_relevant(product: dict, query: str) -> bool:
    """Все слова запроса (с учётом основ) должны встречаться в названии товара."""
    words = query_words(query)
    if not words or is_pet_product(product):
        return False
    name_words = str(product.get("name") or "").casefold().replace(",", " ").split()
    for word in words:
        stem = _stem(word)
        if not any(name_word.startswith(stem) for name_word in name_words):
            return False
    return True


def search_supplements(provider: KuperProvider, query: str, per_store: int = 3) -> list[Offer]:
    """Лучшие релевантные предложения по всем доступным магазинам, от дешёвого."""
    query = " ".join(query.split())[:100]
    if not query:
        return []
    provider._warm()
    offers: list[Offer] = []
    for store in provider.stores():
        try:
            response = provider._session.post(
                f"{BASE}/api/web/v1/products",
                data=json.dumps({"q": query, "store_id": store["id"]}),
                headers=HEADERS,
                timeout=30,
            )
        except Exception:
            continue
        if response.status_code != 200:
            continue
        try:
            products = response.json().get("products") or []
        except ValueError:
            continue
        store_offers = []
        for product in products:
            if not is_relevant(product, query):
                continue
            offer = normalize_product(product, store["name"], store["id"])
            if offer is not None:
                store_offers.append(offer)
        store_offers.sort(key=lambda o: o.price)
        offers.extend(store_offers[:per_store])
        time.sleep(0.3)
    offers.sort(key=lambda o: o.price)
    return offers


def format_supplements(query: str, offers: list[Offer], limit: int = 10) -> str:
    if not offers:
        return (
            f"По «{query}» в магазинах Купера ничего не нашлось. "
            "Попробуйте название без дозировки или другое написание."
        )
    lines = [f"💊 БАД «{query}» — Купер", ""]
    for index, offer in enumerate(offers[:limit], start=1):
        promo = f" · акция −{offer.discount_percent}%" if offer.discount_percent else ""
        lines.append(f"{index}. {offer.price:.0f} ₽ — {offer.store}{promo}")
        lines.append(f"   {offer.name[:90]}")
    lines += ["", DISCLAIMER]
    return "\n".join(lines)
