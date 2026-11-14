"""Аптечный прайс из CSV: только безрецептурные (OTC) препараты.

Формат файла data/pharmacy/prices.csv (UTF-8, с заголовком):
pharmacy,address,name,form,price,in_stock,otc,updated_at

- pharmacy: название аптечной сети;
- address: адрес точки (можно оставить пустым для сети целиком);
- name: название препарата и дозировка;
- form: форма выпуска (таблетки, сироп и т. п.), можно пусто;
- price: цена в рублях, число;
- in_stock: 1/0 (есть в наличии);
- otc: должно быть 1, иначе строка пропускается (рецептурные не показываем);
- updated_at: дата ГГГГ-ММ-ДД, когда цена записана.

Бот не выдаёт медицинских советов: только цена, наличие и дата обновления.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REQUIRED_COLUMNS = {"pharmacy", "address", "name", "form", "price", "in_stock", "otc", "updated_at"}
DISCLAIMER = (
    "Цены из загруженного прайса на дату обновления. Это не медицинская рекомендация: "
    "перед приёмом препарата проконсультируйтесь с врачом или фармацевтом."
)


@dataclass(frozen=True)
class PharmacyOffer:
    pharmacy: str
    address: str
    name: str
    form: str
    price: float
    in_stock: bool
    updated_at: date

    def to_dict(self) -> dict:
        return {
            "pharmacy": self.pharmacy,
            "address": self.address,
            "name": self.name,
            "form": self.form,
            "price": self.price,
            "in_stock": self.in_stock,
            "updated_at": self.updated_at.isoformat(),
        }


def _truthy(value: str) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "да"}


def load_offers(path: Path) -> list[PharmacyOffer]:
    """Читает прайс. Нет файла или неверный заголовок — пустой список, без падения бота."""
    if not path.exists():
        return []
    offers: list[PharmacyOffer] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            return []
        for row in reader:
            if not _truthy(row.get("otc", "")):
                continue
            try:
                price = float(str(row["price"]).replace(",", ".").replace(" ", ""))
                updated = date.fromisoformat(str(row["updated_at"]).strip())
            except (KeyError, ValueError):
                continue
            name = " ".join(str(row.get("name") or "").split())
            if not name or price <= 0:
                continue
            offers.append(
                PharmacyOffer(
                    pharmacy=str(row.get("pharmacy") or "").strip(),
                    address=str(row.get("address") or "").strip(),
                    name=name,
                    form=str(row.get("form") or "").strip(),
                    price=price,
                    in_stock=_truthy(row.get("in_stock", "")),
                    updated_at=updated,
                )
            )
    return offers


def search(offers: list[PharmacyOffer], query: str, limit: int = 10) -> list[PharmacyOffer]:
    """Поиск по подстроке без учёта регистра; сначала есть в наличии, затем по цене."""
    needle = " ".join(query.split()).casefold()
    if not needle:
        return []
    found = [o for o in offers if needle in o.name.casefold()]
    found.sort(key=lambda o: (not o.in_stock, o.price))
    return found[:limit]


def format_results(query: str, offers: list[PharmacyOffer]) -> str:
    if not offers:
        return (
            f"По «{query}» в прайсе аптек ничего нет. "
            "Проверьте название или попробуйте другой вариант написания."
        )
    lines = [f"💊 «{query}» — цены в аптеках (только безрецептурные)", ""]
    for index, offer in enumerate(offers, start=1):
        stock = "в наличии" if offer.in_stock else "нет в наличии"
        where = offer.pharmacy + (f", {offer.address}" if offer.address else "")
        lines.append(f"{index}. {offer.price:.0f} ₽ — {where}")
        lines.append(f"   {offer.name} · {stock} · на {offer.updated_at.strftime('%d.%m.%Y')}")
    lines += ["", DISCLAIMER]
    return "\n".join(lines)
