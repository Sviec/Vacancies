"""Роутер резюме."""

from fastapi import APIRouter

# Эндпоинты добавляются на этапах 5 и 10 (разделы 5.2–5.4 ТЗ)
router = APIRouter(prefix="/resumes", tags=["resumes"])
