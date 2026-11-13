from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonStore:
    """Простой JSON-файл состояния (корзины, offset, последний поиск)."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Any:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def save(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(self.path)


class BasketStore:
    """Корзины пользователей: {user_id: [item, ...]}."""

    def __init__(self, path: Path):
        self.store = JsonStore(path)

    def _all(self) -> dict[str, list[dict]]:
        data = self.store.load()
        return data if isinstance(data, dict) else {}

    def get(self, user_id: int) -> list[dict]:
        return list(self._all().get(str(user_id), []))

    def add(self, user_id: int, item: dict) -> list[dict]:
        baskets = self._all()
        items = baskets.get(str(user_id), [])
        for existing in items:
            if existing.get("store_id") == item.get("store_id") and existing.get("sku") == item.get(
                "sku"
            ):
                existing["qty"] = int(existing.get("qty", 1)) + int(item.get("qty", 1))
                break
        else:
            items.append(dict(item))
        baskets[str(user_id)] = items
        self.store.save(baskets)
        return items

    def set_qty(self, user_id: int, store_id: str, sku: str, qty: int) -> list[dict]:
        baskets = self._all()
        items = baskets.get(str(user_id), [])
        kept = []
        for existing in items:
            if existing.get("store_id") == store_id and existing.get("sku") == sku:
                if qty > 0:
                    existing["qty"] = qty
                    kept.append(existing)
            else:
                kept.append(existing)
        baskets[str(user_id)] = kept
        self.store.save(baskets)
        return kept

    def remove(self, user_id: int, store_id: str, sku: str) -> list[dict]:
        return self.set_qty(user_id, store_id, sku, 0)

    def clear(self, user_id: int) -> None:
        baskets = self._all()
        baskets[str(user_id)] = []
        self.store.save(baskets)


class LastSearchStore:
    """Последний поиск пользователя — нужен для кнопок «в корзину»."""

    def __init__(self, path: Path):
        self.store = JsonStore(path)

    def save(self, user_id: int, query: str, offers: list[dict]) -> None:
        data = self.store.load()
        if not isinstance(data, dict):
            data = {}
        data[str(user_id)] = {"query": query, "offers": offers}
        self.store.save(data)

    def get(self, user_id: int) -> dict | None:
        data = self.store.load()
        if not isinstance(data, dict):
            return None
        entry = data.get(str(user_id))
        return entry if isinstance(entry, dict) else None


class OffsetStore:
    """Offset для getUpdates — чтобы сессии GitHub Actions не теряли сообщения."""

    def __init__(self, path: Path):
        self.store = JsonStore(path)

    def get(self) -> int | None:
        data = self.store.load()
        if isinstance(data, dict) and isinstance(data.get("offset"), int):
            return data["offset"]
        return None

    def set(self, offset: int) -> None:
        self.store.save({"offset": offset})


def basket_totals(items: list[dict]) -> dict[str, float]:
    """Суммы по магазинам."""
    totals: dict[str, float] = {}
    for item in items:
        store = str(item.get("store") or "?")
        totals[store] = totals.get(store, 0.0) + float(item.get("price") or 0) * int(
            item.get("qty", 1)
        )
    return totals


def grand_total(items: list[dict]) -> float:
    return sum(float(item.get("price") or 0) * int(item.get("qty", 1)) for item in items)
