from datetime import date
from pathlib import Path

from price_bot import pharmacy

HEADER = "pharmacy,address,name,form,price,in_stock,otc,updated_at\n"


def write_csv(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "prices.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    return path


def test_missing_or_bad_header_gives_empty(tmp_path):
    assert pharmacy.load_offers(tmp_path / "none.csv") == []
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    assert pharmacy.load_offers(bad) == []


def test_rx_and_broken_rows_are_skipped(tmp_path):
    path = write_csv(
        tmp_path,
        "Сеть А,Адрес 1,Парацетамол 500 мг,таблетки,89.90,1,1,2026-11-10\n"
        "Сеть А,Адрес 1,Рецептурный препарат,таблетки,500,1,0,2026-11-10\n"
        "Сеть Б,,Парацетамол 500 мг,таблетки,abc,1,1,2026-11-10\n"
        "Сеть Б,,Ибупрофен 200 мг,таблетки,120,0,1,не-дата\n"
        "Сеть Б,,Ибупрофен 200 мг,таблетки,120,0,1,2026-11-10\n",
    )
    offers = pharmacy.load_offers(path)
    names = [o.name for o in offers]
    assert names == ["Парацетамол 500 мг", "Ибупрофен 200 мг"]
    assert offers[0].price == 89.90
    assert offers[0].updated_at == date(2026, 11, 10)


def test_search_prefers_in_stock_then_cheapest(tmp_path):
    path = write_csv(
        tmp_path,
        "Сеть А,,Ибупрофен 200 мг,таблетки,150,1,1,2026-11-10\n"
        "Сеть Б,,Ибупрофен 200 мг,таблетки,90,0,1,2026-11-10\n"
        "Сеть В,,Ибупрофен 200 мг,таблетки,120,1,1,2026-11-10\n",
    )
    found = pharmacy.search(pharmacy.load_offers(path), "ибупрофен")
    assert [o.pharmacy for o in found] == ["Сеть В", "Сеть А", "Сеть Б"]


def test_empty_query_and_no_match(tmp_path):
    offers = pharmacy.load_offers(write_csv(tmp_path, ""))
    assert pharmacy.search(offers, "   ") == []
    text = pharmacy.format_results("нет такого", [])
    assert "ничего нет" in text


def test_format_contains_disclaimer_and_no_markdown(tmp_path):
    path = write_csv(tmp_path, "Сеть А,Адрес 1,Аспирин 500 мг,таблетки,99,1,1,2026-11-10\n")
    text = pharmacy.format_results(
        "аспирин", pharmacy.search(pharmacy.load_offers(path), "аспирин")
    )
    assert "99 ₽" in text
    assert "10.11.2026" in text
    assert "не медицинская рекомендация" in text
    assert "*" not in text and "_" not in text
