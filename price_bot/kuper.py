from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

BASE = "https://web.kuper.ru"
HEADERS = {
    "content-type": "application/json",
    "accept": "application/json",
    "referer": f"{BASE}/",
    "origin": BASE,
    "x-requested-with": "XMLHttpRequest",
}

# Топ-10 супермаркетов РФ для сравнения (порядок — как в задании).
TOP10 = [
    "Пятёрочка",
    "Перекрёсток",
    "Магнит",
    "Лента",
    "Ашан",
    "Метро",
    "Дикси",
    "Верный",
    "Спар",
    "Окей",
]

# Купер отдаёт часть сетей латиницей.
LATIN_ALIASES = {"metro": "Метро", "spar": "Спар", "okey": "Окей", "auchan": "Ашан"}


def normalize_store_name(raw: str) -> str:
    name = (raw or "").strip()
    lowered = name.casefold()
    for latin, pretty in LATIN_ALIASES.items():
        if latin in lowered:
            return pretty
    for top in TOP10:
        if top.casefold() in lowered:
            return top
    return name


def store_in_top10(raw: str) -> bool:
    lowered = (raw or "").casefold()
    if any(latin in lowered for latin in LATIN_ALIASES):
        return True
    return any(top.casefold() in lowered for top in TOP10)


VOL_RE = [
    (re.compile(r"([\d.]+)\s*кг"), "кг", 1.0),
    (re.compile(r"([\d.]+)\s*мл"), "л", 0.001),
    (re.compile(r"([\d.]+)\s*л"), "л", 1.0),
    (re.compile(r"([\d.]+)\s*г"), "кг", 0.001),
    (re.compile(r"([\d.]+)\s*шт"), "шт", 1.0),
]


def parse_volume(product: dict) -> tuple[str | None, float | None]:
    """Объём товара → (базовая единица, количество). «900 г» → ('кг', 0.9)."""
    text = str(product.get("human_volume") or "").lower().replace(",", ".")
    for pattern, base, mult in VOL_RE:
        match = pattern.search(text)
        if match:
            try:
                return base, float(match.group(1)) * mult
            except ValueError:
                break
    grams = product.get("grams_per_unit")
    if isinstance(grams, (int, float)) and grams > 0:
        return "кг", grams / 1000.0
    return None, None


@dataclass
class Offer:
    store: str
    store_id: str
    name: str
    price: float
    original_price: float | None = None
    discount_percent: int = 0
    unit_price: float | None = None
    unit: str | None = None
    volume: str = ""
    sku: str = ""
    slug: str = ""

    def to_dict(self) -> dict:
        return {
            "store": self.store,
            "store_id": self.store_id,
            "name": self.name,
            "price": self.price,
            "original_price": self.original_price,
            "discount_percent": self.discount_percent,
            "unit_price": self.unit_price,
            "unit": self.unit,
            "volume": self.volume,
            "sku": self.sku,
            "slug": self.slug,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Offer:
        return cls(
            store=data.get("store", ""),
            store_id=str(data.get("store_id", "")),
            name=data.get("name", ""),
            price=float(data.get("price") or 0),
            original_price=data.get("original_price"),
            discount_percent=int(data.get("discount_percent") or 0),
            unit_price=data.get("unit_price"),
            unit=data.get("unit"),
            volume=data.get("volume", ""),
            sku=str(data.get("sku", "")),
            slug=data.get("slug", ""),
        )


def normalize_product(product: dict, store_name: str, store_id: str) -> Offer | None:
    if not product.get("available"):
        return None
    try:
        price = float(product.get("price") or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    unit, amount = parse_volume(product)
    unit_price = round(price / amount, 2) if unit and amount else None
    original = product.get("original_price")
    try:
        original_price = float(original) if original else None
    except (TypeError, ValueError):
        original_price = None
    discount = int(product.get("discount_percent") or 0)
    if not discount and original_price and original_price > price:
        discount = round((1 - price / original_price) * 100)
    return Offer(
        store=store_name,
        store_id=str(product.get("store_id") or store_id),
        name=str(product.get("name") or "").strip(),
        price=price,
        original_price=original_price,
        discount_percent=discount,
        unit_price=unit_price,
        unit=unit,
        volume=str(product.get("human_volume") or ""),
        sku=str(product.get("sku") or ""),
        slug=str(product.get("slug") or ""),
    )


def pick_best(products: list[dict], query: str) -> dict | None:
    """Лучшее совпадение среди доступных товаров: больше слов запроса в названии."""
    available = [p for p in products if p.get("available")]
    if not available:
        return None
    words = [w for w in query.casefold().split() if len(w) > 2]

    def score(product: dict) -> int:
        name = str(product.get("name") or "").casefold()
        return sum(1 for word in words if word in name)

    return max(available, key=score)


class KuperProvider:
    """Живые цены Купера (неофициальный API, защита ServicePipe).

    Требует curl_cffi с имитацией Chrome. Покрытие сетей зависит от точки
    доставки (координаты): в одной точке доступны не все 10 сетей.
    """

    def __init__(self, lat: float = 55.68, lon: float = 37.75):
        from curl_cffi import requests as creq

        self._session = creq.Session(impersonate="chrome")
        self.lat = lat
        self.lon = lon
        self._stores: list[dict] | None = None
        self._warmed = False

    def _warm(self) -> None:
        if self._warmed:
            return
        self._session.get(f"{BASE}/?city_name=moscow", timeout=30)
        self._warmed = True

    def stores(self) -> list[dict]:
        """Магазины топ-10, доступные по заданным координатам."""
        if self._stores is not None:
            return self._stores
        self._warm()
        url = (
            f"{BASE}/api/v3/mweb/shelves?lat={self.lat}&lon={self.lon}"
            "&shelves_codes_to_exclude=alcohol"
        )
        response = self._session.get(
            url, headers={k: v for k, v in HEADERS.items() if k != "content-type"}, timeout=30
        )
        if response.status_code != 200:
            raise RuntimeError(f"Купер: список магазинов недоступен ({response.status_code})")
        data = response.json()
        shop = ((data.get("data") or {}).get("shelves_data") or {}).get("shop") or {}
        stores: list[dict] = []
        seen: set[str] = set()
        for shelf in shop.values():
            retailer = shelf.get("retailer") or {}
            raw_name = retailer.get("name") or ""
            if not store_in_top10(raw_name):
                continue
            name = normalize_store_name(raw_name)
            if name in seen:
                continue
            seen.add(name)
            stores.append({"id": str(shelf.get("id")), "name": name})
        order = {name: index for index, name in enumerate(TOP10)}
        stores.sort(key=lambda s: order.get(s["name"], 99))
        self._stores = stores
        return stores

    def _search_store(self, query: str, store: dict) -> Offer | None:
        try:
            response = self._session.post(
                f"{BASE}/api/web/v1/products",
                data=json.dumps({"q": query, "store_id": store["id"]}),
                headers=HEADERS,
                timeout=30,
            )
        except Exception:
            return None
        if response.status_code != 200:
            return None
        try:
            products = response.json().get("products") or []
        except ValueError:
            return None
        best = pick_best(products, query)
        if best is None:
            return None
        return normalize_product(best, store["name"], store["id"])

    def search(self, query: str) -> list[Offer]:
        """Лучшее предложение по каждому доступному магазину, от дешёвого."""
        offers: list[Offer] = []
        for store in self.stores():
            offer = self._search_store(query, store)
            if offer is not None:
                offers.append(offer)
            time.sleep(0.3)
        offers.sort(key=lambda o: (o.unit_price is None, o.unit_price or o.price))
        return offers

    def search_one(self, query: str, store_id: str, store_name: str) -> Offer | None:
        return self._search_store(query, {"id": store_id, "name": store_name})
