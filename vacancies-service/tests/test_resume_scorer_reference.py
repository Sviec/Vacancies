"""Эталонные резюме `app/data/demo_resumes.json` попадают в свои диапазоны оценки."""

import json
from datetime import date
from typing import Any
from uuid import UUID

import pytest

from app.schemas.resumes import ResumeCreate
from app.services.resume_scorer import MarketSkills, ResumeSnapshot, ScoreResult, score_resume
from app.services.resumes import build_resume
from app.utils.skills_dict import DATA_DIR

TODAY = date(2026, 9, 28)
USER_ID = UUID("00000000-0000-0000-0000-00000000d3a0")

# Частотные навыки рынка бэкенд-профиля, как их отдал бы `load_market_skills`.
DEMO_MARKET = MarketSkills(
    basis="target_position",
    sample_size=120,
    top_skills=(
        "python",
        "postgresql",
        "docker",
        "fastapi",
        "django",
        "redis",
        "kubernetes",
        "git",
        "sql",
        "linux",
        "kafka",
        "rabbitmq",
        "celery",
        "rest api",
        "microservices",
        "ci/cd",
        "sqlalchemy",
        "pytest",
        "aiohttp",
        "grpc",
    ),
)


def _load() -> list[dict[str, Any]]:
    with (DATA_DIR / "demo_resumes.json").open(encoding="utf-8") as file:
        data: list[dict[str, Any]] = json.load(file)
    return data


def _score(entry: dict[str, Any], today: date = TODAY) -> ScoreResult:
    resume = build_resume(USER_ID, ResumeCreate.model_validate(entry["payload"]))
    return score_resume(ResumeSnapshot.from_resume(resume), DEMO_MARKET, today)


def test_market_has_twenty_unique_skills() -> None:
    assert len(set(DEMO_MARKET.top_skills)) == 20


def test_reference_keys() -> None:
    assert [entry["key"] for entry in _load()] == ["strong", "medium", "weak"]


@pytest.mark.parametrize("entry", _load(), ids=lambda entry: entry["key"])
def test_reference_resume_in_range(entry: dict[str, Any]) -> None:
    result = _score(entry)
    assert entry["expected"]["min"] <= result.score <= entry["expected"]["max"], result.score


def test_reference_strict_order() -> None:
    strong, medium, weak = (_score(entry).score for entry in _load())
    assert strong > medium > weak


@pytest.mark.parametrize("key", ["strong", "medium"])
def test_current_job_makes_score_stable_over_time(key: str) -> None:
    entry = next(item for item in _load() if item["key"] == key)
    assert _score(entry).score == _score(entry, date(2027, 9, 28)).score
