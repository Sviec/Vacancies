"""Подмена текстов рекомендаций: числа скора остаются у шаблона."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import date

import pytest

from app.schemas.adapters import CriterionFailure
from app.services.resume_scorer import EMPTY_MARKET, ResumeSnapshot, ScoreResult, score_resume
from app.services.resume_scoring import _apply_recommendation_phrases
from app.utils.errors import ExternalServiceError, LLMResponseInvalidError

TODAY = date(2026, 9, 28)


class _Phrases:
    def __init__(self, phrases: list[str]) -> None:
        self.phrases = phrases
        self.calls = 0

    async def phrase_recommendations(self, _failures: Sequence[CriterionFailure]) -> list[str]:
        self.calls += 1
        return list(self.phrases)


class _Raise:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    async def phrase_recommendations(self, _failures: Sequence[CriterionFailure]) -> list[str]:
        self.calls += 1
        raise self.error


class _MustNotCall:
    async def phrase_recommendations(self, _failures: Sequence[CriterionFailure]) -> list[str]:
        raise AssertionError("adapter must not be called")


def _empty() -> ScoreResult:
    return score_resume(
        ResumeSnapshot(
            target_position=None,
            desired_salary_min=None,
            desired_salary_currency=None,
            desired_country=None,
            desired_city=None,
            desired_work_format=None,
            summary=None,
            contacts={},
            experience=(),
            education_count=0,
            course_count=0,
            skills=(),
            language_levels=(),
        ),
        EMPTY_MARKET,
        TODAY,
    )


def _order(result: ScoreResult) -> list[str]:
    by_text = {
        item.recommendation: item.key.value
        for item in result.criteria
        if item.recommendation is not None
    }
    assert len(by_text) == len(result.recommendations)
    return [by_text[text] for text in result.recommendations]


async def test_success_changes_only_recommendation_texts() -> None:
    original = _empty()
    failures = [item for item in original.criteria if item.recommendation is not None]
    assert failures
    phrases = [f"фраза-{index}" for index in range(len(failures))]
    adapter = _Phrases(phrases)
    phrased = await _apply_recommendation_phrases(original, adapter)
    assert adapter.calls == 1
    assert phrased is not original
    assert phrased.score == original.score
    assert phrased.market == original.market
    for old, new in zip(original.criteria, phrased.criteria, strict=True):
        assert new.key == old.key
        assert new.name == old.name
        assert new.weight == old.weight
        assert new.points == old.points
        assert new.issues == old.issues
    by_key = {item.key: item.recommendation for item in phrased.criteria}
    for item, phrase in zip(failures, phrases, strict=True):
        assert by_key[item.key] == phrase
        assert phrase != item.recommendation
    phrase_key = {phrase: item.key.value for item, phrase in zip(failures, phrases, strict=True)}
    assert [phrase_key[text] for text in phrased.recommendations] == _order(original)


async def test_adapter_error_keeps_templates() -> None:
    original = _empty()
    for error in (ExternalServiceError("down"), LLMResponseInvalidError()):
        adapter = _Raise(error)
        phrased = await _apply_recommendation_phrases(original, adapter)
        assert adapter.calls == 1
        assert phrased is original


async def test_length_mismatch_keeps_templates() -> None:
    original = _empty()
    count = sum(item.recommendation is not None for item in original.criteria)
    adapter = _Phrases(["только одна"] * (count - 1))
    phrased = await _apply_recommendation_phrases(original, adapter)
    assert adapter.calls == 1
    assert phrased is original


async def test_other_errors_propagate() -> None:
    adapter = _Raise(RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        await _apply_recommendation_phrases(_empty(), adapter)
    assert adapter.calls == 1


async def test_empty_recommendations_do_not_call_adapter() -> None:
    original = _empty()
    silent = replace(
        original,
        criteria=[item.model_copy(update={"recommendation": None}) for item in original.criteria],
        recommendations=[],
    )
    assert any(item.issues for item in silent.criteria)
    phrased = await _apply_recommendation_phrases(silent, _MustNotCall())
    assert phrased is silent
