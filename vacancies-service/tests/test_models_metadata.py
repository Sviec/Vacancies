"""Офлайн-инварианты схемы: всё проверяется по `Base.metadata`, без БД.

Тесты этого модуля не открывают соединений и не требуют Postgres — офлайновый
инвариант набора, заданный на этапе 1, сохраняется. Проверяется не «работает ли
SQL», а то, что схема не разъехалась с принятыми решениями: состав таблиц,
применённость `naming_convention`, обязательные индексы, отсутствие колонок,
несовместимых с выбранным алгоритмом дедупликации, и корректность
конфигурации enum-колонок.
"""

import enum

import pytest
from sqlalchemy import (
    CheckConstraint,
    Constraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db import models  # noqa: F401 — импорт наполняет Base.metadata
from app.db.base import Base

EXPECTED_TABLES = {
    "sources",
    "vacancies",
    "vacancy_postings",
    "resumes",
    "resume_experience",
    "resume_education",
    "resume_skills",
    "resume_courses",
    "resume_languages",
    "vacancy_matches",
    "user_vacancy_actions",
    "parse_runs",
}

# Индексы и ограничения, на которые опираются запросы этапов 4–6. Имена здесь
# записаны целиком: они же должны получиться из NAMING_CONVENTION, так что
# список одновременно проверяет и соответствие конвенции.
REQUIRED_SCHEMA_OBJECTS = [
    ("vacancies", "ix_vacancies_source"),
    ("vacancies", "ix_vacancies_published_at"),
    ("vacancies", "ix_vacancies_country_city"),
    ("vacancy_postings", "uq_vacancy_postings_source_external_id"),
    ("vacancy_postings", "uq_vacancy_postings_source_content_hash"),
    ("vacancy_postings", "ix_vacancy_postings_vacancy_id_source"),
    ("resumes", "uq_resumes_primary_per_user"),
]

GIN_INDEXES = [
    ("vacancies", "ix_vacancies_skills"),
    ("vacancies", "ix_vacancies_search_vector"),
]

# Колонки `NormalizedVacancy`, которые по решению о дедупликации живут только
# на уровне публикации. Их появление в `vacancies` означало бы возврат к
# склейке по `content_hash` описания и расхождение схемы с алгоритмом.
FORBIDDEN_VACANCY_COLUMNS = {"content_hash", "external_id", "raw_payload"}


def _named_objects(table: Table) -> dict[str, Constraint | Index]:
    """Собрать ограничения и индексы таблицы в отображение «имя -> объект»."""
    objects: dict[str, Constraint | Index] = {}
    for constraint in table.constraints:
        if constraint.name is not None:
            objects[str(constraint.name)] = constraint
    for index in table.indexes:
        if index.name is not None:
            objects[str(index.name)] = index
    return objects


def _is_unique(obj: Constraint | Index) -> bool:
    """Гарантирует ли объект уникальность значений.

    `UniqueConstraint`, в отличие от `Index`, атрибута `unique` не имеет:
    уникальность для него — сам тип объекта.
    """
    if isinstance(obj, UniqueConstraint):
        return True
    return isinstance(obj, Index) and bool(obj.unique)


def test_metadata_contains_exactly_expected_tables():
    """Состав таблиц совпадает с разделом 4 ТЗ плюс `vacancy_postings`, без лишних."""
    assert set(Base.metadata.tables) == EXPECTED_TABLES


@pytest.mark.parametrize("table_name", sorted(EXPECTED_TABLES))
def test_primary_key_follows_naming_convention(table_name: str):
    """PK назван `pk_<table>` — прямое доказательство, что конвенция применена."""
    table = Base.metadata.tables[table_name]
    assert table.primary_key.name == f"pk_{table_name}"


@pytest.mark.parametrize(("table_name", "object_name"), REQUIRED_SCHEMA_OBJECTS)
def test_required_schema_objects_exist(table_name: str, object_name: str):
    """Обязательные индексы и UNIQUE присутствуют под ожидаемыми именами."""
    assert object_name in _named_objects(Base.metadata.tables[table_name])


def test_dedup_key_is_unique():
    """`dedup_key` уникален: это цель `ON CONFLICT` при склейке публикаций."""
    dedup_key_constraint = _named_objects(Base.metadata.tables["vacancies"])[
        "uq_vacancies_dedup_key"
    ]
    assert _is_unique(dedup_key_constraint)


@pytest.mark.parametrize(("table_name", "index_name"), GIN_INDEXES)
def test_gin_indexes_use_gin_access_method(table_name: str, index_name: str):
    """Индексы по массиву навыков и по tsvector должны быть GIN, а не btree."""
    index = _named_objects(Base.metadata.tables[table_name])[index_name]
    assert isinstance(index, Index)
    assert index.dialect_options["postgresql"]["using"] == "gin"


@pytest.mark.parametrize("column_name", sorted(FORBIDDEN_VACANCY_COLUMNS))
def test_vacancies_has_no_posting_level_columns(column_name: str):
    """Канон не содержит полей уровня публикации.

    Защита от «возврата как в ТЗ»: `content_hash` в `vacancies` вместе с
    UNIQUE по нему сделал бы склейку по хешу описания невозможной физически,
    а `external_id` и `raw_payload` привязали бы канон к одному источнику.
    """
    assert column_name not in Base.metadata.tables["vacancies"].columns


def test_all_datetime_columns_are_timezone_aware():
    """Ни одной naive-временной колонки во всей схеме.

    Инвариант растёт вместе со схемой и страхует правило DTZ из ruff: оно
    запрещает naive `utcnow()` в коде, но ничего не знает про DDL.
    """
    naive = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, DateTime) and not column.type.timezone
    ]
    assert naive == []


def test_all_foreign_keys_cascade_on_delete():
    """Каждый FK удаляется каскадом: сирот в схеме быть не может."""
    non_cascading = [
        f"{table.name}.{constraint.name}"
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint) and constraint.ondelete != "CASCADE"
    ]
    assert non_cascading == []


def test_enum_columns_are_varchar_with_check():
    """Enum-колонки — VARCHAR + CHECK, а не нативный PG ENUM."""
    misconfigured = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, Enum)
        and not (column.type.native_enum is False and column.type.create_constraint is True)
    ]
    assert misconfigured == []


def test_enum_columns_store_values_not_member_names():
    """В БД пишутся значения членов (`remote`), а не их имена (`REMOTE`).

    Прямая ловля пропущенного `values_callable`: без него `type.enums`
    содержал бы UPPER_CASE-имена и CHECK не пропустил бы ни одного значения
    из контракта раздела 3 ТЗ.
    """
    enum_columns = [
        (table, column)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, Enum)
    ]
    assert enum_columns, "в схеме не найдено ни одной enum-колонки"

    for table, column in enum_columns:
        column_type = column.type
        assert isinstance(column_type, Enum)
        enum_class = column_type.enum_class
        assert enum_class is not None, f"{table.name}.{column.name}: не привязан класс перечисления"
        assert issubclass(enum_class, enum.StrEnum)
        expected = [member.value for member in enum_class]
        assert list(column_type.enums) == expected, f"{table.name}.{column.name}"


def test_every_check_constraint_is_named():
    """У каждого CHECK есть имя.

    Шаблон `ck_%(table_name)s_%(constraint_name)s` требует `name=`; безымянный
    CHECK получил бы имя, зависящее от порядка отражения схемы, и `downgrade`
    автогенерируемой миграции сломался бы.
    """
    unnamed = [
        table.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and not constraint.name
    ]
    assert unnamed == []


@pytest.mark.parametrize("table_name", sorted(EXPECTED_TABLES))
def test_create_table_compiles_for_postgresql(table_name: str):
    """DDL каждой таблицы компилируется под PostgreSQL без соединения.

    Ловит битые `server_default` и некорректное выражение `Computed`
    (генерируемая колонка `search_vector`) вообще без базы.
    """
    table = Base.metadata.tables[table_name]
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert f"CREATE TABLE {table_name}" in ddl
