"""Словари `app/data/*.json`: загрузка, инварианты, валидация ошибок."""

from typing import Any

import pytest

from app.utils.skills_dict import build_skills_dictionary, load_skills_dictionary
from app.utils.vocab import build_vocabulary, load_vocabulary


def _vocab_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "company_legal_forms": ["ооо"],
        "cities": {"Москва": {"country": "Россия", "aliases": ["мск"]}},
        "experience_level_patterns": {"junior": ["junior"]},
        "work_format_patterns": [{"value": "remote", "patterns": ["remote"]}],
        "employment_type_patterns": [{"value": "full_time", "patterns": ["full-time"]}],
        "relocation_patterns": ["relocation"],
    }
    data.update(overrides)
    return data


def test_skills_dictionary_loads() -> None:
    dictionary = load_skills_dictionary()
    canons = set(dictionary.canon_by_alias.values())
    assert len(canons) >= 80
    assert all(canon == canon.lower() for canon in canons)
    assert dictionary.canon_by_alias["питон"] == "python"
    assert load_skills_dictionary() is dictionary


def test_skills_dictionary_is_immutable() -> None:
    dictionary = load_skills_dictionary()
    with pytest.raises(TypeError):
        dictionary.canon_by_alias["new"] = "x"  # type: ignore[index]


def test_excluded_aliases_are_not_searched_in_text() -> None:
    dictionary = load_skills_dictionary()
    searched = {canon for _, canon in dictionary.extraction_patterns}
    assert "c" in dictionary.canon_by_alias
    assert "c" not in searched
    assert "r" not in searched


def test_case_sensitive_tokens_are_searched_only_in_exact_case() -> None:
    dictionary = load_skills_dictionary()
    insensitive = {pattern.pattern for pattern, _ in dictionary.extraction_patterns}
    exact = [(pattern.pattern, canon) for pattern, canon in dictionary.case_sensitive_patterns]
    assert "(?<![\\w+#.])go(?![\\w+#]|\\.\\w)" not in insensitive
    assert any("golang" in pattern for pattern in insensitive)
    assert ("(?<![\\w+#.])Go(?![\\w+#]|\\.\\w)", "go") in exact
    assert exact == sorted(exact, key=lambda item: (-len(item[0]), item[0]))
    assert "cv" in dictionary.text_extraction_exclude
    assert dictionary.canon_by_alias["cv"] == "computer vision"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"skills": {"python": ["py"], "pypy": ["py"]}}, "maps to both"),
        ({"skills": {"python": ["java"], "java": []}}, "is itself a canon"),
        ({"skills": {"Python": []}}, "normalized lowercase"),
        ({"skills": {"": []}}, "normalized lowercase"),
        ({"skills": {"python": ["  "]}}, "empty synonym"),
        ({"skills": {"python": "py"}}, "list of strings"),
        ({"skills": []}, "expected an object"),
        ({"skills": {"python": []}, "text_extraction_exclude": ["go"]}, "not in the dictionary"),
        (
            {"skills": {"python": []}, "text_extraction_case_sensitive": ["Go"]},
            "text_extraction_case_sensitive: 'Go' is not in the dictionary",
        ),
        (
            {"skills": {"python": []}, "text_extraction_case_sensitive": "Go"},
            "list of strings",
        ),
    ],
)
def test_skills_dictionary_validation(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_skills_dictionary(data)


def test_vocabulary_loads() -> None:
    vocabulary = load_vocabulary()
    assert vocabulary.city_by_key["спб"].name == "Санкт-Петербург"
    assert vocabulary.city_by_key["москва"].country == "Россия"
    assert load_vocabulary() is vocabulary
    with pytest.raises(TypeError):
        vocabulary.city_by_key["x"] = vocabulary.city_by_key["москва"]  # type: ignore[index]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "cities": {
                    "Москва": {"country": "Россия", "aliases": ["столица"]},
                    "Минск": {"country": "Беларусь", "aliases": ["Столица"]},
                }
            },
            "maps to both",
        ),
        ({"experience_level_patterns": {"junior": ["джуниор", "ёлка"]}}, "without 'ё'"),
        ({"experience_level_patterns": {"junior": ["Junior"]}}, "lowercase"),
        ({"experience_level_patterns": {"unknown": ["x"]}}, "not detectable"),
        ({"experience_level_patterns": []}, "expected an object"),
        ({"cities": []}, "expected an object"),
        ({"cities": {"Москва": {"country": 1}}}, "string or null"),
        ({"cities": {"Москва": {"aliases": ["  "]}}}, "empty alias"),
        ({"work_format_patterns": {}}, "expected a list"),
        ({"work_format_patterns": [{"patterns": []}]}, "expected"),
        ({"relocation_patterns": "relocation"}, "list of strings"),
    ],
)
def test_vocabulary_validation(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_vocabulary(_vocab_data(**overrides))


def test_vocabulary_invalid_enum_value() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        build_vocabulary(_vocab_data(work_format_patterns=[{"value": "space", "patterns": []}]))
