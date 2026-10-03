"""Адаптеры внешних систем (раздел 9 ТЗ).

Импорт пакета не создаёт HTTP-клиент и не читает секреты: фабрики
вызываются из Depends уже в момент запроса.
"""

from app.adapters.llm import LLMAdapter, MockLLMAdapter, RealLLMAdapter, build_llm_adapter
from app.adapters.profile import (
    MockProfileAdapter,
    ProfileAdapter,
    RealProfileAdapter,
    build_profile_adapter,
)

__all__ = [
    "LLMAdapter",
    "MockLLMAdapter",
    "MockProfileAdapter",
    "ProfileAdapter",
    "RealLLMAdapter",
    "RealProfileAdapter",
    "build_llm_adapter",
    "build_profile_adapter",
]
