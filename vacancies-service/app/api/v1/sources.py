"""Роутер источников вакансий."""

from fastapi import APIRouter

# Эндпоинты добавляются на этапе 11 (раздел 5.1 ТЗ)
router = APIRouter(prefix="/sources", tags=["sources"])
