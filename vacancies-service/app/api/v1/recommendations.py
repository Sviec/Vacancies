"""Роутер рекомендаций вакансий под резюме."""

from fastapi import APIRouter

# GET /vacancies/recommended — этап 6 (раздел 5.6 ТЗ)
router = APIRouter(prefix="/vacancies", tags=["recommendations"])
