"""Канонизация навыков резюме перед записью (`prepare_skills`)."""

from app.schemas.resumes import ResumeSkillCreate
from app.services.resumes import prepare_skills


def _skills(*items: tuple[str, int | None]) -> list[ResumeSkillCreate]:
    return [ResumeSkillCreate(skill=skill, level=level) for skill, level in items]


def test_skill_is_canonicalized() -> None:
    assert prepare_skills(_skills(("Python", 4))) == [("python", 4)]


def test_aliases_collapse_with_first_non_null_level() -> None:
    result = prepare_skills(_skills(("js", None), ("JavaScript", 3), ("javascript", 5)))
    assert result == [("javascript", 3)]


def test_first_level_wins_when_set() -> None:
    assert prepare_skills(_skills(("python", 2), ("Python", 5))) == [("python", 2)]


def test_order_of_first_appearance_is_kept() -> None:
    result = prepare_skills(_skills(("Docker", None), ("python", 1), ("js", 2), ("docker", 3)))
    assert [skill for skill, _ in result] == ["docker", "python", "javascript"]
    assert result[0] == ("docker", 3)


def test_blank_skills_are_dropped() -> None:
    assert prepare_skills(_skills(("   ", 3), ("python", None))) == [("python", None)]
    assert prepare_skills([]) == []
