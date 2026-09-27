"""Описание, уровень, опыт, формат, занятость, релокация (п. 5.5–5.7 плана этапа 4)."""

import pytest

from app.enums import EmploymentType, ExperienceLevel, WorkFormat
from app.services.normalizer import (
    clean_description,
    detect_employment_type,
    detect_experience_level,
    detect_level_from_title,
    detect_relocation,
    detect_work_format,
    extract_experience_years,
    level_from_years,
)
from app.utils.text import city_key_base, remove_emoji, strip_edge_junk, unify_dashes

L = ExperienceLevel


def test_clean_description_reference() -> None:
    raw = (
        "**Python** dev 🔥\n\n\n\n## Требования\n- FastAPI\n• PostgreSQL\n"
        "[сайт](https://x.ru) #python #remote C#"
    )
    assert clean_description(raw) == ("Python dev\n\nТребования\n- FastAPI\n• PostgreSQL\nсайт C#")


def test_clean_description_markdown_details() -> None:
    raw = (
        "![logo](https://x.ru/l.png) Команда\r\n"
        "* пункт\r"
        "```python\nprint(1)\n```\n"
        "`snake_case` и ~~старое~~ __важно__\u00a0\u00a0тут"
    )
    assert clean_description(raw) == (
        "logo Команда\n- пункт\n\nprint(1)\n\nsnake_case и старое важно тут"
    )


@pytest.mark.parametrize(
    ("title", "years", "expected"),
    [
        ("Стажёр-аналитик", None, L.INTERN),
        ("Python Intern", None, L.INTERN),
        ("Junior Python Developer", 5, L.JUNIOR),
        ("Джун фронтендер", None, L.JUNIOR),
        ("Младший аналитик", None, L.JUNIOR),
        ("Middle Backend Developer", None, L.MIDDLE),
        ("Миддл Go-разработчик", None, L.MIDDLE),
        ("Senior Data Scientist", None, L.SENIOR),
        ("Senior-разработчик", None, L.SENIOR),
        ("Ведущий инженер", None, L.SENIOR),
        ("Старший разработчик", None, L.SENIOR),
        ("Сеньор Java", None, L.SENIOR),
        ("Team Lead Backend", None, L.LEAD),
        ("Тимлид", None, L.LEAD),
        ("Head of Data", None, L.LEAD),
        ("Руководитель отдела разработки", None, L.LEAD),
        ("Middle/Senior Python", None, L.MIDDLE),
        ("Intern/Junior QA", None, L.INTERN),
        ("Leading company seeks Python Developer", None, L.UNKNOWN),
        ("International Python Developer", None, L.UNKNOWN),
        ("Python Developer", 0, L.JUNIOR),
        ("Python Developer", 1, L.JUNIOR),
        ("Python Developer", 2, L.MIDDLE),
        ("Python Developer", 3, L.MIDDLE),
        ("Python Developer", 4, L.SENIOR),
        ("Python Developer", 6, L.SENIOR),
        ("Python Developer", 7, L.LEAD),
        ("Python Developer", None, L.UNKNOWN),
    ],
)
def test_detect_experience_level(title: str, years: int | None, expected: ExperienceLevel) -> None:
    assert detect_experience_level(title, years) == expected


def test_level_helpers() -> None:
    assert detect_level_from_title("Python Developer") is None
    assert level_from_years(None) == L.UNKNOWN


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Опыт работы от 3 лет", 3),
        ("Требуется опыт от 1 года", 1),
        ("3+ years of experience", 3),
        ("Опыт 2-4 года", 2),
        ("Опыт 2–4 года", 2),
        ("не менее 5 лет опыта", 5),
        ("5+ лет в разработке", 5),
        ("Без опыта", 0),
        ("Компания основана в 2010 году, бонус 15%", None),
        ("опыт от 99 лет", None),
        ("", None),
    ],
)
def test_extract_experience_years(text: str, expected: int | None) -> None:
    assert extract_experience_years(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Удалёнка или офис в Москве", WorkFormat.REMOTE),
        ("гибрид, 2 дня в офисе", WorkFormat.HYBRID),
        ("Офис м. Тверская", WorkFormat.OFFICE),
        ("", WorkFormat.UNKNOWN),
    ],
)
def test_detect_work_format(text: str, expected: WorkFormat) -> None:
    assert detect_work_format(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("полная занятость", EmploymentType.FULL_TIME),
        ("ГПХ", EmploymentType.CONTRACT),
        ("стажировка", EmploymentType.INTERNSHIP),
        ("неполный день", EmploymentType.PART_TIME),
        ("", EmploymentType.UNKNOWN),
    ],
)
def test_detect_employment_type(text: str, expected: EmploymentType) -> None:
    assert detect_employment_type(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("помощь с релокацией", True), ("", None), ("офис в Москве", None)],
)
def test_detect_relocation(text: str, expected: bool | None) -> None:
    assert detect_relocation(text) is expected


def test_text_primitives() -> None:
    assert unify_dashes("a—b–c−d") == "a-b-c-d"
    assert strip_edge_junk("  «C++!» ") == "C++"
    assert strip_edge_junk("(Backend)!") == "(Backend)"
    assert remove_emoji("№1 👍🏽 ok\ufe0f") == "№1  ok"
    assert city_key_base("  г. Москва ") == "москва"
    assert city_key_base("город Казань") == "казань"
