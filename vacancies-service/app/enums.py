"""Перечисления домена (разделы 3 и 4 ТЗ).

Значения членов совпадают строка-в-строку с `Literal[...]` из схемы
`NormalizedVacancy` (раздел 3) и с допустимыми значениями колонок раздела 4:
именно они, а не имена членов, попадают в БД и в JSON API.

Модуль лежит на верхнем уровне `app/`, а не в `app/db/`, сознательно: те же
классы переиспользует этап 3 в Pydantic-схемах вместо повторного перечисления
`Literal[...]`. Будь модуль внутри `app/db/`, слой схем начал бы импортировать
слой БД — и один источник истины для допустимых значений превратился бы в два
(схемы и модели), которые неизбежно разъехались бы.

`StrEnum` выбран потому, что члены сравниваются и сериализуются как обычные
строки: `SourceType.TELEGRAM == "telegram"` истинно, и сериализация в JSON
не требует ни `.value`, ни кастомного энкодера.
"""

from enum import StrEnum


class SourceType(StrEnum):
    """Тип источника вакансий (раздел 3 ТЗ, поле `source_type`)."""

    TELEGRAM = "telegram"
    HTML = "html"
    API = "api"


class WorkFormat(StrEnum):
    """Формат работы (раздел 3 ТЗ, поле `work_format`)."""

    REMOTE = "remote"
    OFFICE = "office"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class ExperienceLevel(StrEnum):
    """Грейд (раздел 3 ТЗ, поле `experience_level`)."""

    INTERN = "intern"
    JUNIOR = "junior"
    MIDDLE = "middle"
    SENIOR = "senior"
    LEAD = "lead"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    """Тип занятости (раздел 3 ТЗ, поле `employment_type`)."""

    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    UNKNOWN = "unknown"


class SalaryPeriod(StrEnum):
    """Период, к которому отнесена зарплата (раздел 3 ТЗ, поле `salary_period`)."""

    MONTH = "month"
    YEAR = "year"
    HOUR = "hour"


class ParseQuality(StrEnum):
    """Полнота разбора вакансии (раздел 3 ТЗ, поле `parse_quality`)."""

    FULL = "full"
    PARTIAL = "partial"


class UserAction(StrEnum):
    """Действие пользователя над вакансией (п. 5.7 ТЗ)."""

    VIEWED = "viewed"
    SAVED = "saved"
    HIDDEN = "hidden"
    APPLIED = "applied"


class LanguageLevel(StrEnum):
    """Уровень владения языком (раздел 4 ТЗ, `resume_languages.level`)."""

    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"
    NATIVE = "native"


class RunStatus(StrEnum):
    """Статус запуска парсера (раздел 4 ТЗ, `parse_runs.status`)."""

    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ResumeOrigin(StrEnum):
    """Происхождение резюме: ручное, сгенерированное ИИ (п. 5.3) или копия (п. 5.2)."""

    MANUAL = "manual"
    GENERATED = "generated"
    DUPLICATED = "duplicated"
