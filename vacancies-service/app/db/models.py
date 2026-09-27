"""ORM-модели сервиса (раздел 4 ТЗ с двумя осознанными отклонениями).

Отклонение 1 — дедупликация. Раздел 3 ТЗ предписывает склейку по
`content_hash` от `title + company + description_clean`. Это отменено:
один и тот же оффер в разных Telegram-каналах почти всегда переписан своими
словами (сокращён, дополнен эмодзи, переформулирован), поэтому хеш описания
не совпал бы практически никогда и дедупликация не работала бы вовсе.
Принята склейка по нормализованной тройке `company + title + city`.

Отклонение 2 — форма таблиц. Вместо одной плоской `vacancies` схема разделена
на каноническую `vacancies` (оффер, то что видит пользователь) и
`vacancy_postings` (по строке на каждое появление оффера в источнике).
`NormalizedVacancy` раздела 3 остаётся контрактом парсера и описывает
**публикацию**; `vacancies` — плоская проекция публикации-победителя.

Правила, зафиксированные в схеме (реализация выбора победителя — этап 4/5):
победитель среди публикаций — `parse_quality='full'`, среди таких максимальная
длина `description_clean`; поля проигравших публикаций в канон не подмешиваются;
при неопределённой компании `dedup_key IS NULL` и такая вакансия не склеивается
никогда; склейка глобальна во времени, без окна.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)

# ARRAY берётся из диалекта postgresql, а не из корня sqlalchemy: типы
# идентичны по DDL (`TEXT[]`), но диалектная версия несёт компараторы
# `contains`/`overlap`/`contained_by`, без которых фильтр `skills[]`
# из п. 5.5 пришлось бы писать сырым SQL.
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.enums import (
    EmploymentType,
    ExperienceLevel,
    LanguageLevel,
    ParseQuality,
    ResumeOrigin,
    RunStatus,
    SalaryPeriod,
    SourceType,
    UserAction,
    WorkFormat,
)


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Источник вакансий: Telegram-канал, сайт или API (раздел 4, п. 5.1 ТЗ)."""

    __tablename__ = "sources"

    slug: Mapped[str] = mapped_column(String(64))

    # Раздел 4 ТЗ называет эту колонку `type`. Переименована в `source_type`
    # ради единообразия с `vacancies.source_type` и `vacancy_postings.source_type`:
    # одно и то же значение под двумя разными именами в трёх таблицах — гарантия
    # опечатки в запросах этапа 5. Плюс `type` затеняет встроенное имя Python.
    source_type: Mapped[SourceType] = mapped_column(enum_column(SourceType, name="source_type"))

    # Всё, что отличает один источник от другого, живёт здесь, а не в Python:
    # для Telegram `{channel, limit, keywords_filter}`, для HTML
    # `{url, list_selector, fields, pagination}` (п. 5.1 ТЗ). Новый сайт — новая
    # строка в этой таблице, а не новая ветка в парсере.
    # О правке отдельных ключей JSONB — см. TODO у `type_annotation_map` в base.py.
    config: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))

    is_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    last_run_at: Mapped[datetime | None] = mapped_column()
    last_run_status: Mapped[RunStatus | None] = mapped_column(
        enum_column(RunStatus, name="last_run_status")
    )
    last_error: Mapped[str | None] = mapped_column(Text)

    runs: Mapped[list["ParseRun"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (UniqueConstraint("slug"),)


class Vacancy(UUIDPrimaryKeyMixin, Base):
    """Каноническая вакансия — оффер, склеенный из одной или нескольких публикаций.

    Плоская проекция публикации-победителя плюс агрегаты по всем публикациям
    (`published_at`, `last_seen_at`, `postings_count`).
    """

    __tablename__ = "vacancies"

    # TODO: отклонение от раздела 3 ТЗ. Ключ дедупликации — нормализованная
    # тройка `company + title + city`, а не sha256 от описания. Причина: между
    # Telegram-каналами один оффер перепечатывается своими словами, и хеш
    # описания не совпадает никогда — дедупликация по нему давала бы 0 склеек.
    #
    # TODO: неизвестный город даёт **пустую третью компоненту** ключа, а не
    # выпадение города из ключа. Иначе склейка стала бы транзитивной: одна
    # безгородная публикация «Company/Backend» связала бы между собой
    # «Company/Backend/Москва» и «Company/Backend/Петербург» — две разные
    # вакансии в двух офисах слились бы в одну.
    dedup_key: Mapped[str | None] = mapped_column(String(64))

    # Исходная тройка до хеширования — единственный способ разобрать ложную
    # склейку по логам, не переписывая нормализатор.
    dedup_key_raw: Mapped[str | None] = mapped_column(Text)

    title: Mapped[str] = mapped_column(String(500))

    # NULL означает «компания не определена». Такая вакансия получает
    # `dedup_key IS NULL` и не склеивается ни с чем — лучше показать два
    # дубля, чем склеить два разных оффера безымянных компаний.
    company: Mapped[str | None] = mapped_column(String(255))

    description_clean: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)

    # TODO: `source` — обычная строка, FK на `sources.slug` сознательно нет.
    # FK связал бы порядок сида и порядок парсинга (нельзя записать вакансию
    # раньше, чем создан источник) ради целостности, которую и так держит
    # сервисный слой: строка сюда попадает из `BaseParser.source_slug`.
    source: Mapped[str] = mapped_column(String(64))
    source_type: Mapped[SourceType] = mapped_column(enum_column(SourceType, name="source_type"))

    country: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    work_format: Mapped[WorkFormat] = mapped_column(
        enum_column(WorkFormat, name="work_format"),
        server_default=WorkFormat.UNKNOWN.value,
    )
    relocation_support: Mapped[bool | None] = mapped_column(Boolean)

    # TODO: риск переполнения int4 (max 2 147 483 647) для валют с крупным
    # номиналом: годовая вилка в VND или IDR выходит за границу. Лечится
    # `ALTER TABLE ... ALTER COLUMN ... TYPE bigint` без потери данных; сейчас
    # int4 оставлен, потому что источники сида дают RUB/USD/EUR за месяц.
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[SalaryPeriod | None] = mapped_column(
        enum_column(SalaryPeriod, name="salary_period")
    )
    salary_is_gross: Mapped[bool | None] = mapped_column(Boolean)

    skills: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    experience_min_years: Mapped[int | None] = mapped_column(SmallInteger)
    experience_level: Mapped[ExperienceLevel] = mapped_column(
        enum_column(ExperienceLevel, name="experience_level"),
        server_default=ExperienceLevel.UNKNOWN.value,
    )
    employment_type: Mapped[EmploymentType] = mapped_column(
        enum_column(EmploymentType, name="employment_type"),
        server_default=EmploymentType.UNKNOWN.value,
    )
    education_required: Mapped[str | None] = mapped_column(String(255))
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))

    # TODO: `parse_quality` отдельно не агрегируется — это значение публикации-
    # победителя. Поскольку победитель выбирается из `full`, значение здесь
    # автоматически равно `full`, если хотя бы одна публикация разобрана полностью.
    parse_quality: Mapped[ParseQuality] = mapped_column(
        enum_column(ParseQuality, name="parse_quality"),
        server_default=ParseQuality.FULL.value,
    )

    # TODO: `published_at` — **самая ранняя** публикация (MIN по postings), а не
    # последняя. MAX позволил бы любому каналу, перепостившему трёхмесячное
    # объявление, поднять свежесть до максимальных 8 баллов п. 5.6 ТЗ и
    # вытеснить действительно новые вакансии из рекомендаций. Признак «оффер
    # ещё жив» несёт `last_seen_at` (MAX по postings) — это разные вопросы.
    published_at: Mapped[datetime | None] = mapped_column()
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # TODO: `postings_count` добавлен сверх раздела 4 ТЗ — денормализация ради
    # бейджа «N источников» на карточке ленты без коррелированного агрегата по
    # `vacancy_postings` в горячем запросе п. 5.5. Пересчитывается там же, где
    # вставляется публикация.
    postings_count: Mapped[int] = mapped_column(Integer, server_default=text("1"))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Жизненный цикл вакансии — снятие флага, а не DELETE: удаление порвало бы
    # `user_vacancy_actions` пользователя и историю матчинга.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    # Объявлена после `title` и `description_clean`: PostgreSQL требует, чтобы
    # выражение генерируемой колонки ссылалось только на объявленные выше колонки.
    #
    # Двойной словарь `russian` + `english` выбран потому, что заголовки
    # двуязычные внутри одной строки («Frontend-разработчик (React)»): один
    # `russian` калечит английские термины, а `simple` не стеммит вовсе.
    # `setweight` нужен, чтобы `ts_rank` на этапе 5 ставил совпадение в
    # заголовке выше совпадения в теле — это и есть `sort=relevance` п. 5.5 ТЗ.
    #
    # TODO: полнотекстовый поиск ищет только по тексту публикации-победителя.
    # Формулировка, встречающаяся лишь в проигравшей перепечатке, не найдётся.
    # Приемлемо: победитель — самое полное описание оффера.
    #
    # `deferred=True` обязателен: иначе каждый SELECT по вакансиям тащит вектор
    # (килобайты на строку) в память приложения, где он не нужен вообще —
    # ранжирование и фильтрация целиком происходят в PostgreSQL.
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('russian', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('russian', coalesce(description_clean, '')), 'B') || "
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(description_clean, '')), 'B')",
            persisted=True,
        ),
        deferred=True,
        nullable=False,
    )

    postings: Mapped[list["VacancyPosting"]] = relationship(
        back_populates="vacancy",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    matches: Mapped[list["VacancyMatch"]] = relationship(
        back_populates="vacancy",
        cascade="all",
        passive_deletes=True,
    )
    actions: Mapped[list["UserVacancyAction"]] = relationship(
        back_populates="vacancy",
        cascade="all",
        passive_deletes=True,
    )

    __table_args__ = (
        # UNIQUE обычный, не частичный, и это не баг: PostgreSQL по умолчанию
        # трактует NULL как различные значения (NULLS DISTINCT), поэтому
        # произвольное число строк с `dedup_key IS NULL` (компания не
        # определена) помещается в таблицу без конфликтов. Частичный индекс
        # `WHERE dedup_key IS NOT NULL` дал бы ровно то же поведение, но не
        # годился бы целью для `ON CONFLICT (dedup_key)` в upsert этапа 4.
        UniqueConstraint("dedup_key"),
        CheckConstraint(
            "salary_max IS NULL OR salary_min IS NULL OR salary_max >= salary_min",
            name="salary_range",
        ),
        CheckConstraint(
            "(salary_min IS NULL OR salary_min >= 0) AND (salary_max IS NULL OR salary_max >= 0)",
            name="salary_non_negative",
        ),
        CheckConstraint(
            "salary_currency IS NULL OR salary_currency = upper(salary_currency)",
            name="currency_upper",
        ),
        CheckConstraint(
            "experience_min_years IS NULL OR experience_min_years BETWEEN 0 AND 60",
            name="experience_years_range",
        ),
        CheckConstraint("postings_count >= 1", name="postings_count_positive"),
        Index(None, "published_at"),
        Index(None, "source"),
        Index(None, "skills", postgresql_using="gin"),
        Index(None, "search_vector", postgresql_using="gin"),
        # Составной (country, city), а не два одиночных: фильтр п. 5.5 задаёт
        # город почти всегда вместе со страной, а ведущая колонка обслуживает
        # и запрос только по стране.
        Index(None, "country", "city"),
        # Индексов на `experience_level`, `employment_type`, `work_format`,
        # `is_active` и `salary_min` сознательно нет: кардинальность 2–6
        # значений, планировщик на таком распределении всё равно выберет seq
        # scan или bitmap-скан по другому условию, а каждый лишний индекс
        # замедляет вставку в парсинге. Вернуться на этапе 5 по фактическому
        # `EXPLAIN (ANALYZE)` на сид-данных, а не по предположениям.
    )


class VacancyPosting(UUIDPrimaryKeyMixin, Base):
    """Одно появление оффера в конкретном источнике.

    Прямое отображение `NormalizedVacancy` раздела 3 ТЗ. Таблица отвечает на
    два вопроса, на которые плоская `vacancies` ответить не может: «по каким
    ссылкам этот оффер опубликован» (блок «Источники» на карточке) и «почему
    две публикации склеились» (разбор ложного матча по `dedup_key_raw`).

    `TimestampMixin` здесь не используется: `updated_at` не заводится, потому
    что `last_seen_at` полностью покрывает смысл «когда публикацию видели в
    источнике последний раз», а второй штамп с близкой семантикой только
    путал бы — при каждом обходе источника обновлялись бы оба.

    Инвариант: нормализованные поля (`skills`, зарплата, уровни, локация,
    языки) на уровне публикации **не** дублируются. Это допустимо именно
    потому, что публикация хранит полный вход нормализатора — `title`,
    `company`, `description_raw`, `description_clean`, `published_at`,
    `raw_payload`. Значит `normalizer.py` этапа 4 способен восстановить
    канонические поля из любой публикации, и смена победителя не требует
    повторного обращения к источнику.
    """

    __tablename__ = "vacancy_postings"

    vacancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(64))
    source_type: Mapped[SourceType] = mapped_column(enum_column(SourceType, name="source_type"))
    external_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text)

    # `title` и `company` дублируются на уровне публикации не по небрежности:
    # при смене победителя канонический `vacancies.title` копируется именно
    # отсюда, а при разборе ложного склеивания нужно видеть, как каждый канал
    # назвал вакансию, — по одному каноническому заголовку это неразличимо.
    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str | None] = mapped_column(String(255))

    description_raw: Mapped[str] = mapped_column(Text)
    description_clean: Mapped[str] = mapped_column(Text)

    published_at: Mapped[datetime | None] = mapped_column()

    # Без server_default сознательно: это фактическое время парсинга из
    # `NormalizedVacancy.parsed_at`, то есть данные от парсера, а не
    # бухгалтерская отметка о вставке строки. Дефолт `now()` маскировал бы
    # ошибку парсера, не заполнившего поле.
    parsed_at: Mapped[datetime] = mapped_column()

    parse_quality: Mapped[ParseQuality] = mapped_column(
        enum_column(ParseQuality, name="parse_quality"),
        server_default=ParseQuality.FULL.value,
    )

    content_hash: Mapped[str] = mapped_column(String(64))

    raw_payload: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())

    vacancy: Mapped["Vacancy"] = relationship(back_populates="postings")

    __table_args__ = (
        # Идентичность публикации внутри источника; цель `ON CONFLICT` при
        # повторном обходе канала — второй проход по тем же постам обновляет
        # `last_seen_at`, а не плодит строки.
        UniqueConstraint("source", "external_id"),
        # Именно составной, и это принципиально. Глобальный UNIQUE на
        # `content_hash` был бы прямым багом: два канала, перепечатавшие текст
        # дословно, обязаны дать **две** публикации с двумя ссылками — это и
        # есть содержимое блока «Источники» на карточке, ради которого таблица
        # заведена. Составной ловит другой случай — перепост того же текста в
        # том же канале под новым `external_id`.
        UniqueConstraint("source", "content_hash"),
        # Один индекс на три задачи: загрузка блока «Источники» и пересчёт
        # победителя (по ведущей колонке), фильтр `source[]` п. 5.5 через
        # EXISTS (по обеим колонкам), обслуживание каскадного DELETE.
        #
        # Отдельного `ix_vacancy_postings_source` нет: `source` — ведущая
        # колонка обоих UNIQUE выше, чего достаточно и для
        # `SELECT DISTINCT source` в `/vacancies/filters/meta`.
        Index(None, "vacancy_id", "source"),
    )


class Resume(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Резюме пользователя (раздел 4, п. 5.2 ТЗ).

    Коллекции секций резюме (`experience`, `education`, `skills`, `courses`,
    `languages`) объявлены с `delete-orphan`: это части резюме, которые редактор
    этапа 8 создаёт и удаляет целиком вместе с владельцем. Следствие: такие
    строки создаются **через коллекцию родителя** (`resume.skills.append(...)`)
    либо SQL-уровневым INSERT; прямой `session.add(ResumeSkill(resume_id=...))`
    без привязки к объекту резюме SQLAlchemy считает сиротой и роняет flush —
    учесть в сервисном слое этапа 5.

    Коллекция `matches` из этого правила исключена, см. комментарий у неё.
    """

    __tablename__ = "resumes"

    # Без FK: пользователи живут в `profile-core-service` (раздел 9 ТЗ).
    # Авторизации в сервисе нет (п. 0.2), `user_id` всегда передаётся
    # в сервисный слой явно.
    user_id: Mapped[uuid.UUID] = mapped_column()

    title: Mapped[str] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    # Добавлено сверх раздела 4 ТЗ: п. 5.3 требует, чтобы сгенерированное
    # резюме сохранялось «со статусом сгенерировано», а п. 5.2 — операции
    # дублирования. Без колонки оба состояния были бы неотличимы от ручного.
    origin: Mapped[ResumeOrigin] = mapped_column(
        enum_column(ResumeOrigin, name="origin"),
        server_default=ResumeOrigin.MANUAL.value,
    )

    target_position: Mapped[str | None] = mapped_column(String(255))
    desired_salary_min: Mapped[int | None] = mapped_column(Integer)
    desired_salary_currency: Mapped[str | None] = mapped_column(String(3))
    desired_country: Mapped[str | None] = mapped_column(String(100))
    desired_city: Mapped[str | None] = mapped_column(String(100))

    # NULL без дефолта, в отличие от `vacancies.work_format`: «не указано» —
    # значимое состояние, критерий «Конкретность целей» п. 5.4 ТЗ начисляет
    # балл именно за заполненность. Дефолт `unknown` сделал бы незаполненное
    # поле неотличимым от осознанного «мне всё равно» и завысил бы оценку.
    desired_work_format: Mapped[WorkFormat | None] = mapped_column(
        enum_column(WorkFormat, name="desired_work_format")
    )

    summary: Mapped[str | None] = mapped_column(Text)

    # Добавлено сверх раздела 4 ТЗ: критерий «Полнота заполнения» п. 5.4 прямо
    # перечисляет контакты одним из ключевых блоков (вес 2.0 делится на пять
    # блоков), а колонки под них в разделе 4 нет — без неё этап 6 не смог бы
    # посчитать свою часть балла вообще. Форму содержимого задаёт
    # Pydantic-схема этапа 3, а не БД.
    contacts: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))

    # Float по букве раздела 4 ТЗ. Воспроизводимость оценки (критерий приёмки 5)
    # обеспечивает округление внутри `resume_scorer.py`, а не тип колонки:
    # скорер отдаёт уже округлённое до 0.1 значение, поэтому двоичная
    # неточность float не выходит за пределы округления.
    score: Mapped[float | None] = mapped_column(Float)
    score_details: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))

    experience: Mapped[list["ResumeExperience"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    education: Mapped[list["ResumeEducation"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    skills: Mapped[list["ResumeSkill"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    courses: Mapped[list["ResumeCourse"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    languages: Mapped[list["ResumeLanguage"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # Без `delete-orphan`, в отличие от остальных коллекций: vacancy_matches —
    # это кэш (п. 5.6), который этап 6 наполняет bulk-upsert'ом
    # `insert().on_conflict_do_update()`, а не через коллекцию родителя. С
    # `delete-orphan` SQLAlchemy считала бы такую строку сиротой и роняла flush.
    # Удаление при удалении резюме обеспечивает FK ON DELETE CASCADE.
    matches: Mapped[list["VacancyMatch"]] = relationship(
        back_populates="resume",
        cascade="all",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 10", name="score_range"),
        CheckConstraint(
            "desired_salary_min IS NULL OR desired_salary_min >= 0",
            name="desired_salary_non_negative",
        ),
        CheckConstraint(
            "desired_salary_currency IS NULL "
            "OR desired_salary_currency = upper(desired_salary_currency)",
            name="desired_currency_upper",
        ),
        Index(None, "user_id"),
        # Ровно одно основное резюме на пользователя (п. 5.2 ТЗ). Частичный
        # индекс, а не CHECK: правило межстрочное.
        #
        # Ловушка для этапа 5: unique-индекс нельзя объявить DEFERRABLE, поэтому
        # смена основного резюме делается **двумя** операторами в одной
        # транзакции — сначала снять флаг со всех резюме пользователя, затем
        # поставить новому. Один `UPDATE ... SET is_primary = (id = :x)` упадёт
        # на промежуточном состоянии: PostgreSQL проверяет уникальность
        # построчно, а не в конце оператора.
        Index(
            "uq_resumes_primary_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )


class ResumeExperience(UUIDPrimaryKeyMixin, Base):
    """Позиция в опыте работы (раздел 4 ТЗ)."""

    __tablename__ = "resume_experience"

    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    company: Mapped[str] = mapped_column(String(255))
    position: Mapped[str] = mapped_column(String(255))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    description: Mapped[str | None] = mapped_column(Text)
    achievements: Mapped[str | None] = mapped_column(Text)

    resume: Mapped["Resume"] = relationship(back_populates="experience")

    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date > start_date", name="end_after_start"),
        CheckConstraint("NOT is_current OR end_date IS NULL", name="current_has_no_end"),
        # (resume_id, start_date): выдача опыта всегда идёт по резюме и
        # сортируется по дате начала; проверка хронологии п. 5.4 читает тот же
        # порядок. `start_date` NOT NULL, поэтому обратный скан для DESC точен.
        Index(None, "resume_id", "start_date"),
        # Проверка «даты не в будущем» (п. 5.2 ТЗ) в БД **не** реализована и
        # реализована быть не может: CHECK не имеет права ссылаться на `now()`,
        # выражение обязано быть IMMUTABLE — иначе `ALTER TABLE ... VALIDATE` и
        # восстановление дампа давали бы разный результат. Это валидация
        # Pydantic-схемы этапа 3. Написано явно, чтобы этап 3 не счёл, что
        # проверка уже выполняется в БД.
    )


class ResumeEducation(UUIDPrimaryKeyMixin, Base):
    """Образование (раздел 4 ТЗ)."""

    __tablename__ = "resume_education"

    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    institution: Mapped[str] = mapped_column(String(255))
    degree: Mapped[str | None] = mapped_column(String(255))
    field: Mapped[str | None] = mapped_column(String(255))
    start_year: Mapped[int | None] = mapped_column(SmallInteger)
    end_year: Mapped[int | None] = mapped_column(SmallInteger)

    resume: Mapped["Resume"] = relationship(back_populates="education")

    __table_args__ = (
        CheckConstraint(
            "(start_year IS NULL OR start_year BETWEEN 1900 AND 2100) "
            "AND (end_year IS NULL OR end_year BETWEEN 1900 AND 2100)",
            name="year_range",
        ),
        # `>=`, а не `>`: годичная программа начинается и заканчивается в
        # одном календарном году.
        CheckConstraint(
            "start_year IS NULL OR end_year IS NULL OR end_year >= start_year",
            name="end_after_start",
        ),
        Index(None, "resume_id"),
    )


class ResumeSkill(UUIDPrimaryKeyMixin, Base):
    """Навык в резюме (раздел 4 ТЗ)."""

    __tablename__ = "resume_skills"

    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    skill: Mapped[str] = mapped_column(String(100))

    # Nullable сознательно: пользователь вправе не оценивать свой уровень.
    # NOT NULL с дефолтом 3 означал бы выдуманные данные, которые скорер п. 5.4
    # принял бы за настоящие.
    level: Mapped[int | None] = mapped_column(SmallInteger)

    resume: Mapped["Resume"] = relationship(back_populates="skills")

    __table_args__ = (
        UniqueConstraint("resume_id", "skill"),
        CheckConstraint("level IS NULL OR level BETWEEN 1 AND 5", name="level_range"),
        # Раздел 4 ТЗ описывает колонку как «skill (нормализованный)», а матчинг
        # п. 5.6 сравнивает навыки резюме и вакансии обычным равенством строк.
        # Поэтому регистр гарантирует БД, а не дисциплина вызывающего кода:
        # один `Python` вместо `python` молча обнулил бы 45 баллов совпадения.
        CheckConstraint("skill = lower(skill)", name="normalized"),
    )


class ResumeCourse(UUIDPrimaryKeyMixin, Base):
    """Курс или сертификат (раздел 4 ТЗ)."""

    __tablename__ = "resume_courses"

    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str | None] = mapped_column(String(255))
    year: Mapped[int | None] = mapped_column(SmallInteger)
    certificate_url: Mapped[str | None] = mapped_column(Text)

    resume: Mapped["Resume"] = relationship(back_populates="courses")

    __table_args__ = (
        CheckConstraint("year IS NULL OR year BETWEEN 1900 AND 2100", name="year_range"),
        Index(None, "resume_id"),
    )


class ResumeLanguage(UUIDPrimaryKeyMixin, Base):
    """Владение языком (раздел 4 ТЗ)."""

    __tablename__ = "resume_languages"

    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))

    # TODO: `language` — свободная строка без нормализации регистра, в отличие
    # от `resume_skills.skill`. Это осознанно: языки не участвуют в матчинге
    # п. 5.6, критерий «Языки» п. 5.4 требует только наличия хотя бы одного
    # уровня, поэтому сравнение строк нигде не выполняется. Привести к ISO-639-1
    # (`en`, `ru`) и добавить CHECK, если языки войдут в скоринг соответствия.
    language: Mapped[str] = mapped_column(String(50))

    level: Mapped[LanguageLevel] = mapped_column(enum_column(LanguageLevel, name="level"))

    resume: Mapped["Resume"] = relationship(back_populates="languages")

    __table_args__ = (UniqueConstraint("resume_id", "language"),)


class VacancyMatch(UUIDPrimaryKeyMixin, Base):
    """Кэш результата матчинга «резюме × вакансия» (п. 5.6 ТЗ)."""

    __tablename__ = "vacancy_matches"

    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    vacancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)

    # Разбивка по пяти составляющим п. 5.6: какие навыки совпали, каких не
    # хватает. Показывается в UI как ответ на вопрос «почему рекомендовано».
    match_details: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())

    resume: Mapped["Resume"] = relationship(back_populates="matches")
    vacancy: Mapped["Vacancy"] = relationship(back_populates="matches")

    __table_args__ = (
        # Это кэш: ровно одна строка на пару. Ключ конфликта для upsert при
        # пересчёте после изменения резюме или появления новых вакансий.
        UniqueConstraint("resume_id", "vacancy_id"),
        # Главный запрос сервиса — `GET /vacancies/recommended?resume_id=` с
        # сортировкой по убыванию score (п. 5.6). `score` NOT NULL, поэтому
        # обратный скан btree точен и выражение `desc()` в индексе не нужно.
        #
        # TODO: отдельного `ix_vacancy_matches_resume_id` нет — `resume_id`
        # является ведущей колонкой сразу двух индексов выше, так что
        # требование раздела 4 ТЗ («индекс на vacancy_matches.resume_id»)
        # выполнено без третьего дублирующего индекса.
        #
        # TODO: индекса на `vacancy_id` нет: вакансии почти не удаляются
        # (жизненный цикл — `is_active = false`), а разовый каскадный DELETE
        # с seq scan дешевле постоянного сопровождения индекса при каждом
        # пересчёте матчинга. Добавить, если появится массовая чистка старых
        # вакансий.
        Index(None, "resume_id", "score"),
        CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
    )


class UserVacancyAction(UUIDPrimaryKeyMixin, Base):
    """Действие пользователя над вакансией (п. 5.7 ТЗ).

    Действие моделируется как **состояние**, а не как журнал: п. 5.7 говорит
    «скрытые исключаются из выдачи», «сохранённые доступны отдельным списком»,
    то есть требуются множества, а не история. Поэтому UNIQUE по тройке, а
    повторный `viewed` обрабатывается через `ON CONFLICT DO NOTHING` —
    `created_at` остаётся временем первого раза, что и нужно для ответа на
    вопрос «когда пользователь впервые увидел вакансию».
    """

    __tablename__ = "user_vacancy_actions"

    # Без FK: пользователи живут в `profile-core-service` (раздел 9 ТЗ).
    user_id: Mapped[uuid.UUID] = mapped_column()
    vacancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"))
    action: Mapped[UserAction] = mapped_column(enum_column(UserAction, name="action"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    vacancy: Mapped["Vacancy"] = relationship(back_populates="actions")

    __table_args__ = (
        UniqueConstraint("user_id", "vacancy_id", "action"),
        # Отдельный индекс нужен, потому что составной UNIQUE выше его не
        # обслуживает: в нём `action` стоит третьей колонкой, а вторая
        # (`vacancy_id`) в предикате `WHERE user_id = ? AND action = 'hidden'`
        # не участвует — skip scan в PostgreSQL 16 отсутствует, и индекс
        # оказался бы неприменим. Это ровно запросы `exclude_hidden` п. 5.5 и
        # списка сохранённых п. 5.7.
        Index(None, "user_id", "action"),
    )


class ParseRun(UUIDPrimaryKeyMixin, Base):
    """Запуск парсера одного источника (раздел 4, п. 5.1 ТЗ)."""

    __tablename__ = "parse_runs"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column()
    status: Mapped[RunStatus] = mapped_column(enum_column(RunStatus, name="status"))
    items_found: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    items_new: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error_text: Mapped[str | None] = mapped_column(Text)

    source: Mapped["Source"] = relationship(back_populates="runs")

    __table_args__ = (
        CheckConstraint("items_found >= 0 AND items_new >= 0", name="items_non_negative"),
        CheckConstraint("items_new <= items_found", name="items_new_within_found"),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="finished_after_started",
        ),
        # (source_id, started_at): единственный запрос к таблице — история
        # запусков конкретного источника, свежие сверху. `started_at` NOT NULL,
        # обратный скан точен.
        Index(None, "source_id", "started_at"),
    )
