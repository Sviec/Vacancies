"""Декларативная база SQLAlchemy: конвенция имён, миксины, фабрика enum-колонок.

Модуль не импортирует `app.db.models`: цепочка зависимостей строго
`models -> base`, поэтому Alembic (второй проход этапа 2) может импортировать
`Base` отдельно от моделей, а `app.db.session` не зависит ни от того, ни от
другого.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import DateTime, Enum, MetaData, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Конвенция имён обязательна: без неё Alembic присваивает автогенерируемым
# ограничениям и индексам имена, зависящие от порядка отражения схемы, и
# `downgrade` начинает падать на `DROP CONSTRAINT` с несуществующим именем.
#
# Два следствия, которые обязаны соблюдать модели:
#   1. `%(constraint_name)s` требует короткого `name=` у каждого
#      `CheckConstraint` — без него SQLAlchemy падает уже на сборке метаданных,
#      ещё до обращения к БД.
#   2. Шаблон `ix` не умеет именовать индексы по выражениям, поэтому в схеме
#      нет ни одного выражения в индексах — ни `desc()`, ни `lower()`.
#      Для `ORDER BY ... DESC` PostgreSQL сканирует обычный btree в обратную
#      сторону, а все сортируемые колонки внутри составных индексов
#      (`score`, `start_date`, `started_at`) объявлены NOT NULL, так что
#      обратный скан точен. Побочная выгода — исчезает главный источник
#      ложных диффов в `alembic revision --autogenerate`.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Базовый класс всех моделей сервиса."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # `type_annotation_map` — принципиальная вещь, а не удобство: любой
    # `Mapped[datetime]` становится TIMESTAMPTZ по построению, а не по
    # дисциплине автора модели. Naive-времени в схеме не может появиться даже
    # по недосмотру, и правилу DTZ из ruff (запрет naive `utcnow()`) не с чем
    # конфликтовать — колонка физически не умеет хранить время без зоны.
    # ClassVar — требование ruff (RUF012) к изменяемому значению атрибута класса;
    # SQLAlchemy объявляет этот атрибут точно так же.
    #
    # TODO: изменение JSONB на месте (`obj.config["limit"] = 10`) ORM не
    # отслеживает — в сессии нужно присваивать новый dict. Относится ко всем
    # JSONB-колонкам схемы (`sources.config`, `vacancy_postings.raw_payload`,
    # `resumes.contacts`, `resumes.score_details`, `vacancy_matches.match_details`).
    # Если на этапе 6 или 11 понадобится правка отдельных ключей, обернуть
    # соответствующую колонку в `MutableDict.as_mutable(JSONB)`.
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        uuid.UUID: Uuid,
        dict[str, Any]: JSONB,
    }


class UUIDPrimaryKeyMixin:
    """Первичный ключ UUID, генерируемый приложением."""

    # sort_order сдвигает колонку миксина в начало таблицы: иначе SQLAlchemy
    # размещает её после всех колонок модели, и `id` оказывается последним
    # в DDL и в автогенерируемых миграциях — читать такой диff неудобно.
    #
    # TODO: uuid4 вместо упорядоченного uuid7 — в stdlib 3.12 uuid7 отсутствует,
    # а отдельная зависимость ради локальности вставок в btree на ожидаемом
    # объёме (десятки тысяч строк) избыточна. Пересмотреть, если объём вырастет
    # на порядки и фрагментация PK станет заметна в EXPLAIN.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, sort_order=-10)


class TimestampMixin:
    """Пара штампов времени жизни строки."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), sort_order=10)

    # TODO: `updated_at` поддерживается ORM-уровневым `onupdate`, без триггера
    # BEFORE UPDATE. Это корректно, пока все записи идут через ORM; сырых
    # UPDATE в обход сессии в сервисе нет. Если такие появятся (массовый
    # `update()` в задачах парсинга), штамп перестанет обновляться — тогда
    # заводить триггер в отдельной миграции.
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        sort_order=10,
    )


def enum_column[E: StrEnum](py_enum: type[E], *, name: str) -> Enum:
    """Собрать колонку-перечисление как VARCHAR + CHECK.

    Нативный PG ENUM сознательно не используется: `ALTER TYPE ... ADD VALUE`
    Alembic не видит автогенерацией вообще (изменение состава членов даёт пустую
    миграцию), при `downgrade` в базе остаются осиротевшие типы, а состав
    значений здесь будет расширяться — как минимум `employment_type` и
    `experience_level` по мере появления новых источников. VARCHAR + CHECK
    меняется обычным `DROP CONSTRAINT` / `ADD CONSTRAINT` и полностью
    отслеживается автогенерацией.

    Две ловушки, обе критичны и обе решаются только явными аргументами:

    1. `create_constraint` в SQLAlchemy 2.0 по умолчанию **False**. Без явного
       `True` CHECK не создаётся вовсе, и «перечисление» молча превращается в
       свободный varchar, принимающий любую строку.
    2. Без `values_callable` в БД пишутся **имена** членов (`REMOTE`), а не их
       значения (`remote`) — и схема разъезжается с контрактом API раздела 3 ТЗ.

    Фабрика нужна ещё и потому, что экземпляр `Enum` не переиспользуется между
    таблицами: `SchemaType` привязывается к таблице при первом использовании, и
    общий объект на две таблицы даёт один CHECK вместо двух.
    """
    return Enum(
        py_enum,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
        name=name,
    )
