"""Нормализатор: сырая публикация источника → `NormalizedVacancy` (раздел 3 ТЗ).

Только чистые функции: ни времени, ни случайности, ни сети, ни LLM. Одинаковый
вход всегда даёт одинаковый выход — на этом держатся `content_hash`,
`dedup_key` и выбор публикации-победителя в `app/services/ingest.py`.

Словари (навыки, города, паттерны) приходят из `app/data/*.json` через
`load_*()` или параметром; соответствий в этом модуле нет. Регулярные
выражения здесь — грамматика (числа, валюты, периоды), а не словарь.
"""

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, NamedTuple

from app.enums import (
    EmploymentType,
    ExperienceLevel,
    ParseQuality,
    SalaryPeriod,
    SourceType,
    WorkFormat,
)
from app.schemas.normalized import NormalizedVacancy
from app.utils.skills_dict import (
    SkillsDictionary,
    fold_case_keep_length,
    load_skills_dictionary,
    normalize_skill_token,
)
from app.utils.text import (
    city_key_base,
    collapse_spaces,
    fold,
    remove_emoji,
    strip_edge_junk,
    unify_dashes,
)
from app.utils.vocab import Vocabulary, load_vocabulary

# TODO: заголовок, компания и город обрезаются до 500/255/100 символов —
# ширина колонок `vacancies`; длиннее значение в источнике не встречается.
TITLE_MAX_LENGTH = 500
COMPANY_MAX_LENGTH = 255
CITY_MAX_LENGTH = 100

INT4_MAX = 2_147_483_647
EXPERIENCE_YEARS_MAX = 60


# --- Ключ дедупликации и хеш публикации ---

_TITLE_DASH_SPACES_RE = re.compile(r"\s*-\s*")
_COMPANY_QUOTES_RE = re.compile("[«»\"'“”„‘’]")
_CITY_PREFIX_ORIGINAL_RE = re.compile(r"^\s*(?:г\.\s*|г\s+|город\s+)", re.IGNORECASE)


def _legal_forms_regex(forms: tuple[str, ...]) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(form) for form in sorted(forms, key=lambda f: (-len(f), f)))
    return re.compile(rf"\b(?:{alternatives})\b\.?")


def normalize_title_for_key(title: str) -> str:
    """Заголовок для ключа склейки. Грейд и скобки сохраняются — это разные офферы."""
    # TODO: `|` внутри компонент ключа заменяется пробелом — это разделитель
    # компонент в `dedup_key_raw`.
    value = unify_dashes(fold(title)).replace("|", " ")
    # TODO: эмодзи удаляются по всей строке, пунктуация — только по краям;
    # `+` и `#` сохраняются (C++, C#).
    value = collapse_spaces(strip_edge_junk(remove_emoji(value)))
    return _TITLE_DASH_SPACES_RE.sub("-", value)


def normalize_company_for_key(company: str | None, vocab: Vocabulary | None = None) -> str | None:
    """Компания для ключа: без кавычек и ОПФ. Пустая после чистки → `None`."""
    if company is None:
        return None
    vocabulary = vocab or load_vocabulary()
    value = unify_dashes(fold(company)).replace("|", " ")
    value = _COMPANY_QUOTES_RE.sub(" ", value)
    if vocabulary.legal_forms:
        value = _legal_forms_regex(vocabulary.legal_forms).sub(" ", value)
    value = collapse_spaces(strip_edge_junk(remove_emoji(value)))
    return value or None


def normalize_city_for_key(city: str | None, vocab: Vocabulary | None = None) -> str:
    """Город для ключа: канон из словаря, иначе базовая форма. Пусто → `""`."""
    if city is None or not city.strip():
        return ""
    vocabulary = vocab or load_vocabulary()
    base = city_key_base(city)
    entry = vocabulary.city_by_key.get(base)
    return city_key_base(entry.name) if entry is not None else base


def compute_dedup_key(
    company: str | None, title: str, city: str | None
) -> tuple[str | None, str | None]:
    """`(sha256, исходная тройка)`; без компании склейки нет — `(None, None)`."""
    company_key = normalize_company_for_key(company)
    if company_key is None:
        return None, None
    raw = f"{company_key}|{normalize_title_for_key(title)}|{normalize_city_for_key(city)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest(), raw


def compute_content_hash(title: str, company: str | None, description_clean: str) -> str:
    """Идентичность текста публикации в источнике (не ключ склейки)."""
    # TODO: хеш от JSON-массива, а не от конкатенации: ("ab", "c") и
    # ("a", "bc") обязаны давать разные хеши.
    payload = json.dumps(
        [title, company or "", description_clean], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonicalize_city(
    city: str | None, vocab: Vocabulary | None = None
) -> tuple[str | None, str | None]:
    """`(отображаемое имя, страна из словаря)`; город вне словаря — без страны."""
    if city is None or not city.strip():
        return None, None
    vocabulary = vocab or load_vocabulary()
    entry = vocabulary.city_by_key.get(city_key_base(city))
    if entry is not None:
        return entry.name, entry.country
    display = collapse_spaces(_CITY_PREFIX_ORIGINAL_RE.sub("", city))
    return (display or None), None


# --- Зарплата ---


class SalaryParseResult(NamedTuple):
    """Разобранная зарплата; все поля `None` — зарплата не указана."""

    salary_min: int | None
    salary_max: int | None
    currency: str | None
    period: SalaryPeriod | None
    is_gross: bool | None


EMPTY_SALARY = SalaryParseResult(None, None, None, None, None)

_NUMBER_RE = re.compile(
    r"(?<![\d.,])"
    r"(?P<num>\d{1,3}(?:[ .,]\d{3})+(?!\d)|\d+(?:[.,]\d+)?)"
    r"(?P<mult>\s*(?:(?:kk|кк|млн|mln)(?!\w)|тыс\w*\.?|т\.?\s?р(?:\.|(?!\w))|к\b|k\b))?"
)
_THOUSANDS_GROUPED_RE = re.compile(r"^\d{1,3}(?:[ .,]\d{3})+$")
_PERCENT_AFTER_RE = re.compile(r"\s*%")
_MILLION_RE = re.compile(r"kk|кк|млн|mln")
_RUB_MULTIPLIER_RE = re.compile(r"т\.?\s?р")

_CURRENCY_RE = re.compile(
    r"(?P<RUB>₽|руб\w*|\bр\.|\brub\b|\brur\b)"
    r"|(?P<USD>\$|\busd\b|долл\w*|dollar\w*)"
    r"|(?P<EUR>€|\beuro?\b|евро)"
)
_RANGE_FILLER_RE = re.compile(r"[$€₽]|руб\w*\.?|\bр\.|\brub\b|\brur\b|\busd\b|\beuro?\b|евро|\s+")
_RANGE_SEPARATORS = frozenset({"-", "до", "to"})
_FROM_BEFORE_RE = re.compile(r"\b(?:от|from)\s*[$€₽]?\s*$")
_TO_BEFORE_RE = re.compile(r"(?:\bдо|\bup to|\bto)\s*[$€₽]?\s*$")

_PERIOD_RE = re.compile(
    r"(?P<hour>\bв час\b|/\s?час|/\s?ч\b|/\s?h\b|/\s?hr|\bper hour\b|\bhourly\b)"
    r"|(?P<year>\bв год\b|/\s?год|\bper year\b|/\s?year|\bannual\w*|\byearly\b|\bгодов\w*)"
    r"|(?P<month>\bв месяц\b|/\s?мес|\bмес\.|\bper month\b|/\s?month|\bmonthly\b)"
)
# net проверяется раньше gross: «на руки» однозначнее любого «до …».
_NET_RE = re.compile(r"на руки|\bnet\b|чистыми|после вычета|после налог\w*")
_GROSS_RE = re.compile(r"до вычета|\bgross\b|до налог\w*|брутто")

_SALARY_ANCHOR_RE = re.compile(
    r"(?:з/?п|зарплат\w*|оклад\w*|salary|вилк\w*|компенсац\w*|доход\w*)", re.IGNORECASE
)
_SALARY_NEAR_CURRENCY_RE = re.compile(
    r"[$€₽]\s*\d|\d[\d \u00a0.,]*\s*(?:к|k|тыс\.?)?\s*(?:₽|руб|usd|eur|\$|€)", re.IGNORECASE
)


class _Amount(NamedTuple):
    value: Decimal
    multiplier: Decimal | None
    rub_hint: bool
    start: int
    end: int


def _iter_amounts(text: str) -> Iterator[_Amount]:
    for match in _NUMBER_RE.finditer(text):
        if _PERCENT_AFTER_RE.match(text, match.end("num")):
            continue
        raw = match.group("num")
        if _THOUSANDS_GROUPED_RE.match(raw):
            value = Decimal(re.sub(r"[ .,]", "", raw))
        else:
            value = Decimal(raw.replace(",", "."))
        mult_text = (match.group("mult") or "").strip()
        multiplier: Decimal | None = None
        if mult_text:
            multiplier = Decimal(1_000_000) if _MILLION_RE.match(mult_text) else Decimal(1000)
        rub_hint = _RUB_MULTIPLIER_RE.match(mult_text) is not None
        yield _Amount(value, multiplier, rub_hint, match.start(), match.end())


def _to_int(amount: Decimal, multiplier: Decimal | None) -> int:
    scaled = amount * (multiplier if multiplier is not None else Decimal(1))
    return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _detect_currency(text: str, rub_hint: bool) -> str | None:
    match = _CURRENCY_RE.search(text)
    if match is not None:
        return match.lastgroup
    # TODO: валюта без символа и слова → None; RUB выводится только из «т.р.»/«тр».
    return "RUB" if rub_hint else None


def _detect_period(text: str) -> SalaryPeriod:
    match = _PERIOD_RE.search(text)
    if match is not None and match.lastgroup is not None:
        return SalaryPeriod(match.lastgroup)
    # TODO: сумма есть, период не указан → месяц (типичная запись в РФ-вакансиях).
    return SalaryPeriod.MONTH


def _detect_gross(text: str) -> bool | None:
    if _NET_RE.search(text):
        return False
    if _GROSS_RE.search(text):
        return True
    return None


def parse_salary(text: str | None) -> SalaryParseResult:
    """Разобрать строку зарплаты («от 150 000 руб.», «150-200к», «$3000-4000»…)."""
    if text is None or not text.strip():
        return EMPTY_SALARY
    s = unify_dashes(unicodedata.normalize("NFKC", text).lower().replace("ё", "е"))
    amounts = list(_iter_amounts(s))
    if not amounts:
        return EMPTY_SALARY

    first = amounts[0]
    second = amounts[1] if len(amounts) > 1 else None
    if second is not None:
        filler = _RANGE_FILLER_RE.sub("", s[first.end : second.start])
        if filler not in _RANGE_SEPARATORS:
            second = None

    salary_min: int | None
    salary_max: int | None
    if second is not None:
        first_multiplier = first.multiplier
        if first_multiplier is None and second.multiplier is not None and first.value < 1000:
            first_multiplier = second.multiplier
        salary_min = _to_int(first.value, first_multiplier)
        salary_max = _to_int(second.value, second.multiplier)
        if salary_min > salary_max:
            salary_min, salary_max = salary_max, salary_min
        rub_hint = first.rub_hint or second.rub_hint
    else:
        value = _to_int(first.value, first.multiplier)
        prefix = s[: first.start]
        if _FROM_BEFORE_RE.search(prefix):
            salary_min, salary_max = value, None
        elif _TO_BEFORE_RE.search(prefix):
            salary_min, salary_max = None, value
        else:
            # TODO: одно число без «от»/«до» трактуется как фиксированная сумма min=max.
            salary_min = salary_max = value
        rub_hint = first.rub_hint

    # TODO: сумма больше int4 (ширина колонок) → вся зарплата считается неуказанной.
    if any(v is not None and v > INT4_MAX for v in (salary_min, salary_max)):
        return EMPTY_SALARY

    return SalaryParseResult(
        salary_min=salary_min,
        salary_max=salary_max,
        currency=_detect_currency(s, rub_hint),
        period=_detect_period(s),
        is_gross=_detect_gross(s),
    )


def extract_salary_from_text(text: str) -> SalaryParseResult:
    """Найти зарплату в описании: строка с якорем («зарплата», «з/п»…) или с валютой."""
    for line in text.splitlines():
        anchor = _SALARY_ANCHOR_RE.search(line)
        if anchor is not None:
            result = parse_salary(line[anchor.start() :])
        elif _SALARY_NEAR_CURRENCY_RE.search(line):
            result = parse_salary(line)
        else:
            continue
        if result.salary_min is not None or result.salary_max is not None:
            return result
    return EMPTY_SALARY


# --- Навыки ---

_HASHTAG_RE = re.compile(r"(?<![\w&])#([\w-]+)")


def normalize_skills(
    skills: Iterable[str], dictionary: SkillsDictionary | None = None
) -> list[str]:
    """Привести готовый список навыков к канонам; неизвестные — lowercase как есть."""
    skills_dictionary = dictionary or load_skills_dictionary()
    result: list[str] = []
    seen: set[str] = set()
    for skill in skills:
        token = normalize_skill_token(skill)
        if not token:
            continue
        canon = skills_dictionary.canon_by_alias.get(token, token)
        if canon not in seen:
            seen.add(canon)
            result.append(canon)
    return result


def extract_skills(text: str, dictionary: SkillsDictionary | None = None) -> list[str]:
    """Найти навыки словаря в тексте; из пересекающихся совпадений выигрывает длинное."""
    skills_dictionary = dictionary or load_skills_dictionary()
    lowered = fold_case_keep_length(text)
    found: list[tuple[int, int, str]] = [
        (match.start(), match.end(), canon)
        for pattern, canon in skills_dictionary.extraction_patterns
        for match in pattern.finditer(lowered)
    ]
    found.extend(
        (match.start(), match.end(), canon)
        for pattern, canon in skills_dictionary.case_sensitive_patterns
        for match in pattern.finditer(text)
    )
    found.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[2]))

    result: list[str] = []
    seen: set[str] = set()
    covered_until = -1
    for start, end, canon in found:
        if start < covered_until:
            continue
        covered_until = end
        if canon not in seen:
            seen.add(canon)
            result.append(canon)
    return result


def extract_hashtags(text: str) -> list[str]:
    """Тела хештегов (`#machine_learning` → `machine learning`); `C#` — не хештег."""
    return [match.group(1).replace("_", " ") for match in _HASHTAG_RE.finditer(text)]


def skills_from_hashtags(
    hashtags: Iterable[str], dictionary: SkillsDictionary | None = None
) -> list[str]:
    """Навыки из тел хештегов: только точное совпадение с синонимом словаря.

    Хештег — явная метка навыка, поэтому регистр не важен (`#go` → `go`), но
    неоднозначные синонимы из `text_extraction_exclude` (`#cv`) не учитываются,
    а неизвестные теги (`#remote`) отбрасываются.
    """
    skills_dictionary = dictionary or load_skills_dictionary()
    result: list[str] = []
    for hashtag in hashtags:
        token = normalize_skill_token(hashtag)
        canon = skills_dictionary.canon_by_alias.get(token)
        if canon is None or token in skills_dictionary.text_extraction_exclude:
            continue
        if canon not in result:
            result.append(canon)
    return result


# --- Уровень и опыт ---

_EXPERIENCE_NONE_RE = re.compile(r"без опыта|no experience")
_YEARS_UNIT = r"(?:год\w*|лет|years?|yrs)"
_EXPERIENCE_YEARS_RES = (
    re.compile(
        r"(?:опыт\w*|experience)[^\n.]{0,30}?(?<!\d)(\d{1,2})(?:\s*-\s*\d{1,2})?\s*\+?\s*"
        + _YEARS_UNIT
    ),
    re.compile(
        r"(?<!\d)(\d{1,2})(?:\s*-\s*\d{1,2})?\s*\+?\s*"
        + _YEARS_UNIT
        + r"\s+(?:опыт\w*|of experience|experience|коммерческ\w*|в разработк\w*)"
    ),
    re.compile(r"(?<!\d)(\d{1,2})\s*\+\s*(?:лет|год\w*|years?)"),
)


def level_from_years(years: int | None) -> ExperienceLevel:
    """Грейд по минимальному стажу."""
    # TODO: границы полуинтервалами ≤1 junior, ≤3 middle, ≤6 senior, >6 lead;
    # intern из стажа не выводится — только из заголовка.
    if years is None:
        return ExperienceLevel.UNKNOWN
    if years <= 1:
        return ExperienceLevel.JUNIOR
    if years <= 3:
        return ExperienceLevel.MIDDLE
    if years <= 6:
        return ExperienceLevel.SENIOR
    return ExperienceLevel.LEAD


def detect_level_from_title(title: str, vocab: Vocabulary | None = None) -> ExperienceLevel | None:
    """Грейд по заголовку; несколько грейдов («Middle/Senior») → младший."""
    vocabulary = vocab or load_vocabulary()
    folded = fold(unify_dashes(title))
    # TODO: несколько грейдов в заголовке → младший: вакансия «Middle/Senior»
    # доступна middle-кандидату. `level_patterns` упорядочены intern → lead.
    for level, patterns in vocabulary.level_patterns:
        if any(pattern.search(folded) for pattern in patterns):
            return level
    return None


def detect_experience_level(
    title: str, experience_min_years: int | None, vocab: Vocabulary | None = None
) -> ExperienceLevel:
    """Заголовок, иначе стаж, иначе `unknown`."""
    # TODO: уровень ищется только в заголовке — в теле «senior» слишком часто
    # встречается в чужом контексте («работа с senior-командой»).
    from_title = detect_level_from_title(title, vocab)
    if from_title is not None:
        return from_title
    return level_from_years(experience_min_years)


def extract_experience_years(text: str) -> int | None:
    """Минимальный требуемый стаж в годах; самое раннее совпадение в тексте."""
    folded = unify_dashes(fold(text))
    candidates: list[tuple[int, int]] = [
        (match.start(), 0) for match in _EXPERIENCE_NONE_RE.finditer(folded)
    ]
    for pattern in _EXPERIENCE_YEARS_RES:
        for match in pattern.finditer(folded):
            years = int(match.group(1))
            if years <= EXPERIENCE_YEARS_MAX:
                candidates.append((match.start(), years))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


# --- Описание ---

_SPACE_LIKE_TABLE = str.maketrans(dict.fromkeys("\u00a0\u202f\u2009", " "))
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_FENCE_RE = re.compile(r"```[\w+-]*")
_MD_EMPHASIS_RE = re.compile(r"\*\*|__|~~")
_MD_HEADING_RE = re.compile(r"^#{1,6}[ \t]+", re.MULTILINE)
_MD_STAR_ITEM_RE = re.compile(r"^\*[ \t]+", re.MULTILINE)
_HASHTAG_FULL_RE = re.compile(r"(?<![\w&])#[\w-]+")
_INLINE_SPACES_RE = re.compile(r"[ \t]+")
_MANY_NEWLINES_RE = re.compile(r"\n{3,}")


def clean_description(raw: str) -> str:
    """Текст без markdown, хештегов и эмодзи; маркеры списков `- ` и `• ` сохраняются."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n").translate(_SPACE_LIKE_TABLE)
    text = unicodedata.normalize("NFC", text)
    text = _MD_IMAGE_RE.sub(r"\1", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_FENCE_RE.sub("", text).replace("`", "")
    text = _MD_EMPHASIS_RE.sub("", text)
    text = _MD_HEADING_RE.sub("", text)
    text = _MD_STAR_ITEM_RE.sub("- ", text)
    text = _HASHTAG_FULL_RE.sub("", text)
    text = remove_emoji(text)
    lines = [_INLINE_SPACES_RE.sub(" ", line).strip() for line in text.split("\n")]
    return _MANY_NEWLINES_RE.sub("\n\n", "\n".join(lines)).strip()


# --- Формат, занятость, релокация ---


def detect_work_format(text: str, vocab: Vocabulary | None = None) -> WorkFormat:
    """Первая сработавшая категория в порядке `vocab.json`; нет → `unknown`."""
    # TODO: приоритет формата и занятости — порядок категорий в vocab.json
    # («удалёнка или офис» → remote, т.к. remote стоит раньше office).
    vocabulary = vocab or load_vocabulary()
    folded = fold(text)
    for value, patterns in vocabulary.work_format_patterns:
        if any(pattern.search(folded) for pattern in patterns):
            return value
    return WorkFormat.UNKNOWN


def detect_employment_type(text: str, vocab: Vocabulary | None = None) -> EmploymentType:
    """Первая сработавшая категория в порядке `vocab.json`; нет → `unknown`."""
    vocabulary = vocab or load_vocabulary()
    folded = fold(text)
    for value, patterns in vocabulary.employment_patterns:
        if any(pattern.search(folded) for pattern in patterns):
            return value
    return EmploymentType.UNKNOWN


def detect_relocation(text: str, vocab: Vocabulary | None = None) -> bool | None:
    """`True`, если упомянута помощь с релокацией, иначе `None` — никогда `False`."""
    # TODO: отсутствие упоминания не доказывает отсутствие релокации, поэтому
    # из текста выводится только True.
    vocabulary = vocab or load_vocabulary()
    folded = fold(text)
    return True if any(p.search(folded) for p in vocabulary.relocation_patterns) else None


# --- Публикация-победитель ---


@dataclass(frozen=True, slots=True)
class WinnerCandidate:
    """Проекция публикации, достаточная для выбора победителя."""

    source: str
    external_id: str
    parse_quality: ParseQuality
    description_length: int
    published_at: datetime | None


def winner_sort_key(candidate: WinnerCandidate) -> tuple[int, int, bool, float, str, str]:
    """full раньше partial, длиннее описание, раньше дата (без даты — в конец), затем id."""
    return (
        0 if candidate.parse_quality == ParseQuality.FULL else 1,
        -candidate.description_length,
        candidate.published_at is None,
        candidate.published_at.timestamp() if candidate.published_at is not None else 0.0,
        candidate.source,
        candidate.external_id,
    )


def pick_winner(candidates: Sequence[WinnerCandidate]) -> WinnerCandidate:
    """Детерминированный победитель; порядок кандидатов на результат не влияет."""
    if not candidates:
        msg = "pick_winner: no candidates"
        raise ValueError(msg)
    return min(candidates, key=winner_sort_key)


# --- Точка входа ---


@dataclass(frozen=True, slots=True, kw_only=True)
class RawVacancy:
    """Сырой вход нормализатора от парсера.

    Структурные поля (`work_format`, `salary_min`…) заполняет источник, который
    отдаёт их явно (API, HTML с разметкой); явное значение важнее извлечённого
    из текста.
    """

    external_id: str
    source: str
    source_type: SourceType
    title: str
    description_raw: str
    parsed_at: datetime
    url: str | None = None
    company: str | None = None
    city: str | None = None
    country: str | None = None
    salary_text: str | None = None
    # None — источник не отдал список навыков; пустой кортеж — отдал пустой.
    skills_hint: tuple[str, ...] | None = None
    published_at: datetime | None = None
    raw_payload: Mapping[str, Any] = field(default_factory=dict)
    work_format: WorkFormat | None = None
    employment_type: EmploymentType | None = None
    experience_level: ExperienceLevel | None = None
    experience_min_years: int | None = None
    relocation_support: bool | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: SalaryPeriod | None = None
    salary_is_gross: bool | None = None
    education_required: str | None = None
    languages: tuple[str, ...] | None = None


def _is_naive(value: datetime) -> bool:
    return value.tzinfo is None or value.utcoffset() is None


def _explicit_salary(raw: RawVacancy) -> SalaryParseResult:
    salary_min, salary_max = raw.salary_min, raw.salary_max
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        salary_min, salary_max = salary_max, salary_min
    return SalaryParseResult(
        salary_min=salary_min,
        salary_max=salary_max,
        currency=raw.salary_currency.upper() if raw.salary_currency else None,
        period=raw.salary_period,
        is_gross=raw.salary_is_gross,
    )


def normalize_vacancy(
    raw: RawVacancy,
    *,
    skills_dictionary: SkillsDictionary | None = None,
    vocabulary: Vocabulary | None = None,
) -> NormalizedVacancy:
    """Собрать `NormalizedVacancy` из сырой публикации; ошибки схемы пробрасываются."""
    if _is_naive(raw.parsed_at) or (raw.published_at is not None and _is_naive(raw.published_at)):
        msg = "parsed_at and published_at must be timezone-aware"
        raise ValueError(msg)

    title = collapse_spaces(raw.title)[:TITLE_MAX_LENGTH]
    company = collapse_spaces(raw.company)[:COMPANY_MAX_LENGTH] if raw.company else ""
    company_or_none = company or None
    description_clean = clean_description(raw.description_raw)
    text = f"{title}\n{description_clean}"

    city, vocab_country = canonicalize_city(raw.city, vocabulary)
    if city is not None:
        city = city[:CITY_MAX_LENGTH]
    explicit_country = collapse_spaces(raw.country) if raw.country else ""
    country = explicit_country or vocab_country

    if raw.salary_min is not None or raw.salary_max is not None:
        salary = _explicit_salary(raw)
    elif raw.salary_text is not None:
        salary = parse_salary(raw.salary_text)
    else:
        salary = extract_salary_from_text(description_clean)

    experience_min_years = (
        raw.experience_min_years
        if raw.experience_min_years is not None
        else extract_experience_years(text)
    )
    experience_level = (
        raw.experience_level
        if raw.experience_level not in (None, ExperienceLevel.UNKNOWN)
        else detect_experience_level(title, experience_min_years, vocabulary)
    )

    if raw.skills_hint is not None:
        # TODO: явный список навыков источника не сливается с извлечёнными из
        # текста — источник со структурой знает свои навыки точнее словаря.
        skills = normalize_skills(raw.skills_hint, skills_dictionary)
    else:
        skills = extract_skills(text, skills_dictionary)
        for skill in skills_from_hashtags(extract_hashtags(raw.description_raw), skills_dictionary):
            if skill not in skills:
                skills.append(skill)

    work_format = (
        raw.work_format
        if raw.work_format not in (None, WorkFormat.UNKNOWN)
        else detect_work_format(text, vocabulary)
    )
    employment_type = (
        raw.employment_type
        if raw.employment_type not in (None, EmploymentType.UNKNOWN)
        else detect_employment_type(text, vocabulary)
    )
    relocation_support = (
        raw.relocation_support
        if raw.relocation_support is not None
        else detect_relocation(text, vocabulary)
    )

    # TODO: full ⇔ непустые заголовок и описание и известная компания; неполная
    # публикация не отбрасывается, а проигрывает выбор победителя.
    parse_quality = (
        ParseQuality.FULL
        if title and company_or_none is not None and description_clean
        else ParseQuality.PARTIAL
    )

    # TODO: languages и education_required из текста не извлекаются, город —
    # тоже; только явные значения источника.
    return NormalizedVacancy(
        external_id=raw.external_id,
        source=raw.source,
        source_type=raw.source_type,
        url=raw.url,
        title=title,
        company=company_or_none,
        description_raw=raw.description_raw,
        description_clean=description_clean,
        country=country,
        city=city,
        work_format=work_format or WorkFormat.UNKNOWN,
        relocation_support=relocation_support,
        salary_min=salary.salary_min,
        salary_max=salary.salary_max,
        salary_currency=salary.currency,
        salary_period=salary.period,
        salary_is_gross=salary.is_gross,
        skills=skills,
        experience_min_years=experience_min_years,
        experience_level=experience_level or ExperienceLevel.UNKNOWN,
        employment_type=employment_type or EmploymentType.UNKNOWN,
        education_required=raw.education_required,
        languages=list(raw.languages or ()),
        published_at=raw.published_at,
        parsed_at=raw.parsed_at,
        parse_quality=parse_quality,
        raw_payload=dict(raw.raw_payload),
        content_hash=compute_content_hash(title, company_or_none, description_clean),
    )
