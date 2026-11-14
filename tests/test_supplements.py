from price_bot.kuper import normalize_product
from price_bot.supplements import DISCLAIMER, format_supplements, is_relevant, query_words


def product(name, price=500, available=True, volume=""):
    return {
        "name": name,
        "price": price,
        "available": available,
        "store_id": "1",
        "human_volume": volume,
        "sku": "x",
        "slug": "x",
    }


def test_query_words_drop_short_tokens():
    assert query_words("БАД омега-3") == ["бад", "омега-3"]
    assert query_words(" ") == []


def test_irrelevant_beer_is_filtered_for_bad_query():
    assert not is_relevant(product("Пиво Bud светлое 440 мл"), "БАД")


def test_inflection_matches_by_stem():
    assert is_relevant(product("Мультивитамины GLS капсулы 60 шт"), "мультивитамин")
    assert is_relevant(product("Витамины D3 и К2 спрей 30 мл"), "витамин D3")


def test_all_words_must_match():
    assert not is_relevant(product("Магний B6 таблетки"), "магний цинк")


def test_unavailable_product_is_not_normalized():
    assert normalize_product(product("Омега 3 капсулы", available=False), "Лента", "1") is None


def test_format_has_disclaimer_and_no_markdown():
    offers = [
        normalize_product(
            product("Омега 3 капсулы 90 шт", price=399, volume="90 шт"), "Лента", "1"
        ),
    ]
    text = format_supplements("омега 3", [o for o in offers if o])
    assert "Лента" in text
    assert DISCLAIMER in text
    assert "*" not in text and "_" not in text


def test_empty_result_message():
    assert "ничего не нашлось" in format_supplements("нет такого", [])


def test_pet_products_are_excluded():
    assert not is_relevant(product("Лакомство Omega для собак маленьких пород 30 г"), "омега")
    assert not is_relevant(product("Корм для кошек с омега 3"), "омега")
