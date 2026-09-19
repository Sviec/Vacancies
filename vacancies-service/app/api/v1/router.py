"""Сборка роутеров версии 1."""

from fastapi import APIRouter

from app.api.v1 import recommendations, resumes, sources, vacancies

api_router = APIRouter(prefix="/api/v1")

# ВАЖЕН ПОРЯДОК: recommendations подключается раньше vacancies, потому что
# маршрут /vacancies/recommended (раздел 5.6 ТЗ) должен матчиться раньше
# /vacancies/{id}. При обратном порядке FastAPI попытается разобрать строку
# "recommended" как id вакансии и вернёт ошибку валидации.
# Не менять порядок при добавлении эндпоинтов на этапах 5 и 6.
api_router.include_router(recommendations.router)
api_router.include_router(vacancies.router)
api_router.include_router(resumes.router)
api_router.include_router(sources.router)
