"""Проверка локальной модели: два черновика должны пройти схему ResumeDraft.

Запуск из vacancies-service, когда Ollama уже слушает 127.0.0.1:11434:

    python -m scripts.check_local_llm
"""

import asyncio
import sys

from app.adapters.llm import RealLLMAdapter
from app.config import Settings
from app.schemas.ai import ResumeGenerateRequest

_SAMPLES = (
    ResumeGenerateRequest(
        raw_text=(
            "Иван Петров, Москва. Python-разработчик 4 года. "
            "Делал API на FastAPI и PostgreSQL в компании Север. "
            "Хочу удалёнку, от 250000 руб."
        ),
        target_position="Python-разработчик",
    ),
    ResumeGenerateRequest(
        raw_text=(
            "Анна Смирнова, аналитик данных. SQL, Python, отчёты в Tableau. "
            "Образование: НИУ ВШЭ, экономика, 2018. Английский B2."
        ),
        target_position="Аналитик данных",
    ),
)


async def main() -> int:
    settings = Settings(
        _env_file=None,
        llm_mode="real",
        llm_base_url="http://127.0.0.1:11434/v1",
        llm_api_key="local",
        llm_model="qwen2.5:7b-instruct",
        llm_timeout_seconds=180,
    )
    adapter = RealLLMAdapter(settings)
    for sample in _SAMPLES:
        draft = await adapter.generate_resume(sample)
        print(f"ok title={draft.title!r} skills={len(draft.skills)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
