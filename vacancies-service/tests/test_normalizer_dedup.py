"""Ключ склейки, хеш публикации и выбор победителя (п. 5.1, 5.8 плана этапа 4)."""

import itertools
from datetime import UTC, datetime

import pytest

from app.enums import ParseQuality
from app.services.normalizer import (
    WinnerCandidate,
    canonicalize_city,
    compute_content_hash,
    compute_dedup_key,
    normalize_city_for_key,
    normalize_company_for_key,
    normalize_title_for_key,
    pick_winner,
)

# Зафиксированы запуском кода; сырая строка сверена с планом, hex — с
# независимым `hashlib.sha256` от этой строки.
YANDEX_SENIOR_MOSCOW_KEY = "1cf3ecb54afa8256c0580b3e029c7eafce8a77367cb0c5efce81c8d7d6f1f69b"
YANDEX_SENIOR_NO_CITY_KEY = "89d59f6c540aa3f8c31fb4ceabf94b43baafe9c07530da69b9f9818773d2ba43"
CONTENT_HASH_WITH_COMPANY = "e5ac2ba72efa7b04143bcc5fd7871277144c98d41b8a82bbab2ae9d3abcbb088"
CONTENT_HASH_NO_COMPANY = "99bf51d755d2f1d8d75252a4754181987a1b9e1c6d4ba8023f3762fce404f4bb"


def test_content_hash_fixed_vectors() -> None:
    assert (
        compute_content_hash("Python Developer", "Яндекс", "Описание вакансии")
        == CONTENT_HASH_WITH_COMPANY
    )
    assert (
        compute_content_hash("Python Developer", None, "Описание вакансии")
        == CONTENT_HASH_NO_COMPANY
    )


def test_content_hash_is_unambiguous() -> None:
    assert compute_content_hash("ab", "c", "") != compute_content_hash("a", "bc", "")


def test_dedup_key_fixed_vector() -> None:
    key, raw = compute_dedup_key("ООО «Яндекс»", "Senior Python Developer", "г. Москва")
    assert raw == "яндекс|senior python developer|москва"
    assert key == YANDEX_SENIOR_MOSCOW_KEY


def test_dedup_key_ignores_noise() -> None:
    key, _ = compute_dedup_key("Яндекс", "  🔥 Senior   Python Developer!! ", "МСК")
    assert key == YANDEX_SENIOR_MOSCOW_KEY


def test_dedup_key_empty_city_is_empty_component() -> None:
    key, raw = compute_dedup_key("Яндекс", "Senior Python Developer", "")
    assert raw == "яндекс|senior python developer|"
    assert key == YANDEX_SENIOR_NO_CITY_KEY
    assert compute_dedup_key("Яндекс", "Senior Python Developer", None)[1] == raw


def test_dedup_key_keeps_grade_and_brackets() -> None:
    senior = compute_dedup_key("Яндекс", "Senior Python Developer", "Москва")
    middle = compute_dedup_key("Яндекс", "Middle Python Developer", "Москва")
    backend = compute_dedup_key("Яндекс", "Python Developer (Backend)", "Москва")
    plain = compute_dedup_key("Яндекс", "Python Developer", "Москва")
    assert senior != middle
    assert backend != plain


@pytest.mark.parametrize("company", [None, "ООО", "  ", "«ООО»"])
def test_dedup_key_without_company(company: str | None) -> None:
    assert compute_dedup_key(company, "Python Developer", "Москва") == (None, None)


def test_city_aliases_share_key() -> None:
    keys = {
        normalize_city_for_key(c) for c in ["Санкт-Петербург", "СПб", "Питер", "Saint Petersburg"]
    }
    assert keys == {"санкт-петербург"}
    assert normalize_city_for_key("  ") == ""
    assert normalize_city_for_key("Урюпинск") == "урюпинск"


def test_title_dashes_unified() -> None:
    assert normalize_title_for_key("Бэкенд — разработчик") == normalize_title_for_key(
        "бэкенд-разработчик"
    )
    assert normalize_title_for_key("C++ | Qt разработчик") == "c++ qt разработчик"


def test_company_legal_forms_and_quotes() -> None:
    assert normalize_company_for_key('ООО "Рога и Копыта"') == "рога и копыта"
    assert normalize_company_for_key("Acme Inc.") == "acme"
    assert normalize_company_for_key("Аонкология") == "аонкология"


@pytest.mark.parametrize(
    ("city", "expected"),
    [
        ("мск", ("Москва", "Россия")),
        ("г. Урюпинск", ("Урюпинск", None)),
        ("  Урюпинск   Центр ", ("Урюпинск Центр", None)),
        ("", (None, None)),
        (None, (None, None)),
        ("г.", (None, None)),
    ],
)
def test_canonicalize_city(city: str | None, expected: tuple[str | None, str | None]) -> None:
    assert canonicalize_city(city) == expected
    if expected[0] is not None and city is not None:
        assert normalize_city_for_key(expected[0]) == normalize_city_for_key(city)


def _candidate(
    external_id: str,
    *,
    quality: ParseQuality = ParseQuality.FULL,
    length: int = 100,
    published_at: datetime | None = None,
    source: str = "tg",
) -> WinnerCandidate:
    return WinnerCandidate(
        source=source,
        external_id=external_id,
        parse_quality=quality,
        description_length=length,
        published_at=published_at,
    )


def test_winner_full_beats_longer_partial() -> None:
    full = _candidate("1", length=10)
    partial = _candidate("2", quality=ParseQuality.PARTIAL, length=10_000)
    assert pick_winner([partial, full]) == full


def test_winner_longer_description() -> None:
    assert pick_winner([_candidate("1", length=10), _candidate("2", length=20)]).external_id == "2"


def test_winner_earlier_date_and_dated_beats_undated() -> None:
    early = _candidate("1", published_at=datetime(2026, 1, 1, tzinfo=UTC))
    late = _candidate("2", published_at=datetime(2026, 2, 1, tzinfo=UTC))
    undated = _candidate("0")
    assert pick_winner([late, undated, early]) == early
    assert pick_winner([undated, late]) == late


def test_winner_tie_break_by_source_and_external_id() -> None:
    a = _candidate("2", source="a")
    b = _candidate("1", source="b")
    c = _candidate("1", source="a")
    assert pick_winner([a, b, c]) == c


def test_winner_independent_of_order() -> None:
    date = datetime(2026, 3, 1, tzinfo=UTC)
    candidates = [
        _candidate("1", length=50, published_at=date),
        _candidate("2", length=50, published_at=date, source="zz"),
        _candidate("3", quality=ParseQuality.PARTIAL, length=500),
        _candidate("4", length=50),
    ]
    winners = {pick_winner(list(p)) for p in itertools.permutations(candidates)}
    assert winners == {candidates[0]}


def test_winner_empty() -> None:
    with pytest.raises(ValueError, match="no candidates"):
        pick_winner([])
