"""Навыки: канонизация готового списка и извлечение из текста (п. 5.4 плана этапа 4)."""

import pytest
from tests.factories import make_normalized

from app.services.normalizer import (
    extract_hashtags,
    extract_skills,
    normalize_skills,
    skills_from_hashtags,
)


def test_normalize_skills() -> None:
    skills = ["Python", "питон", "JS", "PostgreSQL", "postgres", "Unknown-Tool", "  ", "python"]
    assert normalize_skills(skills) == ["python", "javascript", "postgresql", "unknown-tool"]


def test_normalize_skills_keeps_ambiguous_synonyms() -> None:
    assert normalize_skills(["CV", "rest", "shell"]) == ["computer vision", "rest api", "bash"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("JavaScript и TypeScript", ["javascript", "typescript"]),
        ("работаем в Google на Go", ["go"]),
        ("C++, C# и .NET, ASP.NET", ["c++", "c#", ".net", "asp.net"]),
        ("Node.js и Vue.js", ["node.js", "vue"]),
        ("React Native", ["react native"]),
        ("опыт с питоном и кафкой", ["python", "kafka"]),
        ("Python-разработчик", ["python"]),
        ("C и R", []),
        ("С++ (кириллица)", ["c++"]),
        ("k8s, Docker", ["kubernetes", "docker"]),
        ("Docker, Python, docker", ["docker", "python"]),
        ("Machine   Learning и Spring Boot", ["machine learning", "spring boot"]),
        ("", []),
    ],
)
def test_extract_skills(text: str, expected: list[str]) -> None:
    assert extract_skills(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Attach your CV",
        "the rest of the team",
        "rest and relax",
        "shell company",
        "rails of the project",
        "torch bearer",
        "rabbit hole",
        "elastic schedule",
        "let's go",
        "we go further",
        "go to office",
        "swift response",
        "rust belt",
        "spring is coming",
        "gin and tonic",
        "helm of the ship",
        "excel at communication",
        "the train went off the rails",
    ],
)
def test_extract_skills_ignores_common_words(text: str) -> None:
    assert extract_skills(text) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ruby on Rails", ["ruby on rails"]),
        ("Rails 7 developer", ["ruby on rails"]),
        ("Experience with Rails and PostgreSQL", ["ruby on rails", "postgresql"]),
        ("rest api", ["rest api"]),
        ("REST API", ["rest api"]),
        ("RESTful", ["rest api"]),
        ("Go-разработчик", ["go"]),
        ("пишем на Go", ["go"]),
        ("Golang", ["go"]),
        ("Swift", ["swift"]),
        ("Rust", ["rust"]),
        ("Spring Boot", ["spring boot"]),
        ("Spring", ["spring"]),
        ("Helm", ["helm"]),
        ("Excel", ["excel"]),
        ("PyTorch", ["pytorch"]),
        ("RabbitMQ", ["rabbitmq"]),
        ("Elasticsearch", ["elasticsearch"]),
        ("Bash", ["bash"]),
        ("компьютерное зрение", ["computer vision"]),
        ("Computer Vision", ["computer vision"]),
    ],
)
def test_extract_skills_real_mentions(text: str, expected: list[str]) -> None:
    assert extract_skills(text) == expected


def test_extract_skills_positions_survive_length_changing_lowercase() -> None:
    assert extract_skills("İİ Go и Docker") == ["go", "docker"]


def test_extract_hashtags() -> None:
    assert extract_hashtags("#python #machine_learning C# a&#39; #ci-cd") == [
        "python",
        "machine learning",
        "ci-cd",
    ]


@pytest.mark.parametrize(
    ("hashtags", "expected"),
    [
        (["python", "django", "python3"], ["python", "django"]),
        (["go", "rust"], ["go", "rust"]),
        (["rails"], ["ruby on rails"]),
        (["Rails"], ["ruby on rails"]),
        (["machine learning"], ["machine learning"]),
        (["remote", "cv"], []),
        (["python developer"], []),
    ],
)
def test_skills_from_hashtags(hashtags: list[str], expected: list[str]) -> None:
    assert skills_from_hashtags(hashtags) == expected


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Ищем в команду #go #rust", ["go", "rust"]),
        ("Ищем в команду #remote #cv", []),
        ("Стек: Docker, Go #python #docker", ["docker", "go", "python"]),
    ],
)
def test_normalize_vacancy_hashtag_skills(description: str, expected: list[str]) -> None:
    vacancy = make_normalized(title="Разработчик", description_raw=description)
    assert vacancy.skills == expected


def test_normalize_vacancy_rails_posting() -> None:
    vacancy = make_normalized(
        title="Middle Rails Developer",
        description_raw="Ищем Rails-разработчика в команду #rails #ruby",
    )
    assert vacancy.skills == ["ruby on rails", "ruby"]


def test_normalize_vacancy_rails_hashtag_only() -> None:
    vacancy = make_normalized(title="Разработчик", description_raw="Ищем в команду #rails")
    assert vacancy.skills == ["ruby on rails"]
