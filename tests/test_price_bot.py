from __future__ import annotations

from pathlib import Path

from price_bot.bot import fmt_money, short_name
from price_bot.kuper import (
    Offer,
    normalize_product,
    normalize_store_name,
    parse_volume,
    pick_best,
    store_in_top10,
)
from price_bot.store import BasketStore, OffsetStore, basket_totals, grand_total


def test_parse_volume() -> None:
    assert parse_volume({"human_volume": "900 г"}) == ("кг", 0.9)
    assert parse_volume({"human_volume": "970 мл"}) == ("л", 0.97)
    assert parse_volume({"human_volume": "1 л"}) == ("л", 1.0)
    assert parse_volume({"human_volume": "10 шт"}) == ("шт", 10.0)
    assert parse_volume({"grams_per_unit": 500}) == ("кг", 0.5)
    assert parse_volume({}) == (None, None)


def test_store_names() -> None:
    assert normalize_store_name("METRO") == "Метро"
    assert normalize_store_name("Супер Лента") == "Лента"
    assert normalize_store_name("Пятёрочка") == "Пятёрочка"
    assert store_in_top10("Дикси")
    assert store_in_top10("METRO")
    assert not store_in_top10("ВкусВилл Гипермаркет")


def test_normalize_product() -> None:
    product = {
        "available": True,
        "price": 67.6,
        "original_price": 79.9,
        "discount_percent": 15,
        "human_volume": "970 мл",
        "name": "Молоко 1,5% 970 мл",
        "sku": "123",
        "slug": "moloko",
        "store_id": "239791",
    }
    offer = normalize_product(product, "Перекрёсток", "239791")
    assert offer is not None
    assert offer.price == 67.6
    assert offer.discount_percent == 15
    assert offer.unit == "л"
    assert offer.unit_price == round(67.6 / 0.97, 2)
    assert normalize_product({"available": False, "price": 10}, "Магнит", "1") is None
    assert normalize_product({"available": True, "price": 0}, "Магнит", "1") is None


def test_pick_best_prefers_name_match() -> None:
    products = [
        {"available": True, "name": "Молоко 3,2% 1 л"},
        {"available": True, "name": "Сметана 20% 300 г"},
        {"available": False, "name": "Молоко козье"},
    ]
    best = pick_best(products, "молоко")
    assert best is not None
    assert "Молоко" in best["name"]


def test_basket_store(tmp_path: Path) -> None:
    baskets = BasketStore(tmp_path / "baskets.json")
    item = {
        "store": "Перекрёсток",
        "store_id": "1",
        "name": "Молоко",
        "price": 67.6,
        "qty": 1,
        "sku": "123",
    }
    baskets.add(42, item)
    baskets.add(42, dict(item))  # тот же товар — количество растёт
    items = baskets.get(42)
    assert len(items) == 1
    assert items[0]["qty"] == 2
    assert grand_total(items) == 135.2
    assert basket_totals(items) == {"Перекрёсток": 135.2}
    baskets.set_qty(42, "1", "123", 1)
    assert baskets.get(42)[0]["qty"] == 1
    baskets.remove(42, "1", "123")
    assert baskets.get(42) == []
    baskets.add(42, item)
    baskets.clear(42)
    assert baskets.get(42) == []


def test_offset_store(tmp_path: Path) -> None:
    offsets = OffsetStore(tmp_path / "offset.json")
    assert offsets.get() is None
    offsets.set(777)
    assert offsets.get() == 777


def test_offer_roundtrip() -> None:
    offer = Offer(
        store="Ашан",
        store_id="172",
        name="Молоко",
        price=84.99,
        unit_price=94.43,
        unit="л",
        sku="999",
    )
    restored = Offer.from_dict(offer.to_dict())
    assert restored == offer


def test_formatting() -> None:
    assert fmt_money(67.6) == "67.60 ₽"
    assert short_name("а" * 100).endswith("…")
    assert len(short_name("а" * 100)) == 60
