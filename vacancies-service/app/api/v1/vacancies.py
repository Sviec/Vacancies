"""Роутер вакансий."""

from fastapi import APIRouter

# Эндпоинты добавляются на этапах 5 и 6 (разделы 5.5, 5.7 ТЗ)
router = APIRouter(prefix="/vacancies", tags=["vacancies"])
