"""Действия пользователя над вакансиями (п. 5.7 ТЗ): состояние, а не журнал.

Функции только делают flush и не коммитят: границу транзакции задаёт эндпоинт.
"""

import uuid
from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserVacancyAction, Vacancy
from app.enums import UserAction
from app.utils.errors import NotFoundError

_ACTION_ORDER = {action: index for index, action in enumerate(UserAction)}

# TODO: `saved` и `hidden` взаимоисключающие (решение пользователя):
# постановка одного снимает другое.
_MUTUALLY_EXCLUSIVE = {
    UserAction.SAVED: UserAction.HIDDEN,
    UserAction.HIDDEN: UserAction.SAVED,
}


def _sorted_actions(actions: Iterable[UserAction]) -> list[UserAction]:
    """Действия в порядке объявления членов `UserAction`, без повторов."""
    return sorted(set(actions), key=_ACTION_ORDER.__getitem__)


async def _ensure_vacancy(session: AsyncSession, vacancy_id: UUID) -> None:
    # Действия над неактивной вакансией разрешены: проверяется только существование.
    found = await session.scalar(select(Vacancy.id).where(Vacancy.id == vacancy_id))
    if found is None:
        raise NotFoundError(details={"resource": "vacancy", "id": str(vacancy_id)})


async def _pair_actions(session: AsyncSession, user_id: UUID, vacancy_id: UUID) -> list[UserAction]:
    return (await actions_for(session, user_id, [vacancy_id])).get(vacancy_id, [])


async def _delete_action(
    session: AsyncSession, user_id: UUID, vacancy_id: UUID, action: UserAction
) -> None:
    await session.execute(
        delete(UserVacancyAction).where(
            UserVacancyAction.user_id == user_id,
            UserVacancyAction.vacancy_id == vacancy_id,
            UserVacancyAction.action == action,
        )
    )


async def add_action(
    session: AsyncSession, user_id: UUID, vacancy_id: UUID, action: UserAction
) -> list[UserAction]:
    """Поставить действие идемпотентно; `created_at` первого раза сохраняется."""
    await _ensure_vacancy(session, vacancy_id)
    # `id` генерирует Python-дефолт только в ORM, для Core-INSERT — явно.
    stmt = (
        pg_insert(UserVacancyAction)
        .values(id=uuid.uuid4(), user_id=user_id, vacancy_id=vacancy_id, action=action)
        .on_conflict_do_nothing(index_elements=["user_id", "vacancy_id", "action"])
    )
    await session.execute(stmt)
    opposite = _MUTUALLY_EXCLUSIVE.get(action)
    if opposite is not None:
        await _delete_action(session, user_id, vacancy_id, opposite)
    await session.flush()
    return await _pair_actions(session, user_id, vacancy_id)


async def remove_action(
    session: AsyncSession, user_id: UUID, vacancy_id: UUID, action: UserAction
) -> list[UserAction]:
    """Снять действие идемпотентно: отсутствие строки — не ошибка."""
    # TODO: снимается через DELETE .../action/{action} любое из четырёх действий.
    await _ensure_vacancy(session, vacancy_id)
    await _delete_action(session, user_id, vacancy_id, action)
    await session.flush()
    return await _pair_actions(session, user_id, vacancy_id)


async def actions_for(
    session: AsyncSession, user_id: UUID, vacancy_ids: Sequence[UUID]
) -> dict[UUID, list[UserAction]]:
    """Действия пользователя по списку вакансий одним запросом."""
    if not vacancy_ids:
        return {}
    stmt = select(UserVacancyAction.vacancy_id, UserVacancyAction.action).where(
        UserVacancyAction.user_id == user_id,
        UserVacancyAction.vacancy_id.in_(vacancy_ids),
    )
    grouped: dict[UUID, list[UserAction]] = {}
    for vacancy_id, action in (await session.execute(stmt)).all():
        grouped.setdefault(vacancy_id, []).append(action)
    return {vacancy_id: _sorted_actions(actions) for vacancy_id, actions in grouped.items()}
