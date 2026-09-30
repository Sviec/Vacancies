import { Plus, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Checkbox, NumberField, Select, TextArea, TextField } from "@/components/ui/fields";
import { IconButton } from "@/components/ui/IconButton";
import type { ResumeDraft } from "@/features/editor/draft";
import {
  emptyCourse,
  emptyEducation,
  emptyExperience,
  emptyLanguage,
  emptySkill,
} from "@/features/editor/draft";
import { Section } from "@/features/editor/Section";
import { LANGUAGE_LEVEL_LABELS, WORK_FORMAT_LABELS } from "@/lib/labels";
import type { LanguageLevel, WorkFormat } from "@/api/types";

const CONTACT_FIELDS = [
  { key: "email", label: "Email", type: "email" as const },
  { key: "phone", label: "Телефон", type: "tel" as const },
  { key: "telegram", label: "Telegram", type: "text" as const },
  { key: "linkedin", label: "LinkedIn", type: "url" as const },
  { key: "github", label: "GitHub", type: "url" as const },
  { key: "website", label: "Сайт", type: "url" as const },
] as const;

const WORK_FORMAT_OPTIONS: WorkFormat[] = ["remote", "office", "hybrid"];
const LANGUAGE_OPTIONS = Object.keys(LANGUAGE_LEVEL_LABELS) as LanguageLevel[];

interface SectionProps {
  draft: ResumeDraft;
  errors: Record<string, string>;
  today: string;
  onChange: (next: ResumeDraft) => void;
  countries?: string[];
  cities?: string[];
  suggestedSkills?: string[];
}

export function BasicsSection({ draft, errors, onChange }: SectionProps) {
  return (
    <Section
      id="basics"
      number="01"
      title="Основное"
      hint="Название версии, цель и короткий рассказ о себе."
    >
      <div className="grid gap-4 md:grid-cols-2">
        <TextField
          label="Целевая позиция"
          value={draft.target_position}
          error={errors.target_position}
          onChange={(event) => onChange({ ...draft, target_position: event.target.value })}
          placeholder="Senior Python Developer"
          containerClassName="md:col-span-2"
        />
        <TextArea
          label="О себе"
          value={draft.summary}
          error={errors.summary}
          onChange={(event) => onChange({ ...draft, summary: event.target.value })}
          placeholder="2–4 предложения о фокусе и сильных сторонах"
          rows={4}
          containerClassName="md:col-span-2"
        />
        {CONTACT_FIELDS.map((field) => (
          <TextField
            key={field.key}
            label={field.label}
            type={field.type}
            value={draft.contacts[field.key]}
            error={errors[`contacts.${field.key}`]}
            onChange={(event) =>
              onChange({
                ...draft,
                contacts: { ...draft.contacts, [field.key]: event.target.value },
              })
            }
          />
        ))}
      </div>
    </Section>
  );
}

export function GoalsSection({ draft, errors, onChange, countries = [], cities = [] }: SectionProps) {
  return (
    <Section
      id="goals"
      number="02"
      title="Цели"
      hint="Чем точнее цель, тем полезнее рекомендации и поиск вакансий."
    >
      <div className="grid gap-4 md:grid-cols-2">
        <NumberField
          label="Желаемая зарплата от"
          value={draft.desired_salary_min}
          error={errors.desired_salary_min}
          onChange={(event) => onChange({ ...draft, desired_salary_min: event.target.value })}
          placeholder="400000"
        />
        <Select
          label="Валюта"
          value={draft.desired_salary_currency}
          error={errors.desired_salary_currency}
          onChange={(event) => onChange({ ...draft, desired_salary_currency: event.target.value })}
        >
          <option value="">Не указана</option>
          <option value="RUB">RUB</option>
          <option value="USD">USD</option>
          <option value="EUR">EUR</option>
          <option value="KZT">KZT</option>
        </Select>
        <TextField
          label="Страна"
          list="resume-countries"
          value={draft.desired_country}
          error={errors.desired_country}
          onChange={(event) => onChange({ ...draft, desired_country: event.target.value })}
        />
        <datalist id="resume-countries">
          {countries.map((item) => (
            <option key={item} value={item} />
          ))}
        </datalist>
        <TextField
          label="Город"
          list="resume-cities"
          value={draft.desired_city}
          error={errors.desired_city}
          onChange={(event) => onChange({ ...draft, desired_city: event.target.value })}
        />
        <datalist id="resume-cities">
          {cities.map((item) => (
            <option key={item} value={item} />
          ))}
        </datalist>
        <Select
          label="Формат работы"
          value={draft.desired_work_format}
          error={errors.desired_work_format}
          onChange={(event) =>
            onChange({
              ...draft,
              desired_work_format: event.target.value as WorkFormat | "",
            })
          }
        >
          <option value="">Не указан</option>
          {WORK_FORMAT_OPTIONS.map((value) => (
            <option key={value} value={value}>
              {WORK_FORMAT_LABELS[value]}
            </option>
          ))}
        </Select>
      </div>
    </Section>
  );
}

export function ExperienceSection({ draft, errors, today, onChange }: SectionProps) {
  return (
    <Section
      id="experience"
      number="03"
      title="Опыт работы"
      hint="Покажите контекст, вклад и результат. Не обязательно писать длинно."
    >
      <div className="space-y-4">
        {draft.experience.map((item, index) => {
          const prefix = `experience.${index}`;
          return (
            <div key={item.key} className="rounded-lg border border-line bg-canvas p-4">
              <div className="mb-4 flex items-center justify-between gap-3">
                <span className="text-[13px] font-medium text-ink-muted">
                  Место работы {index + 1}
                </span>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-[13px] text-ink-muted hover:text-danger"
                  onClick={() =>
                    onChange({
                      ...draft,
                      experience: draft.experience.filter((_, i) => i !== index),
                    })
                  }
                >
                  <Trash2 size={13} aria-hidden /> Удалить
                </button>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <TextField
                  label="Компания"
                  value={item.company}
                  error={errors[`${prefix}.company`]}
                  onChange={(event) => {
                    const experience = draft.experience.map((row, i) =>
                      i === index ? { ...row, company: event.target.value } : row,
                    );
                    onChange({ ...draft, experience });
                  }}
                />
                <TextField
                  label="Должность"
                  value={item.position}
                  error={errors[`${prefix}.position`]}
                  onChange={(event) => {
                    const experience = draft.experience.map((row, i) =>
                      i === index ? { ...row, position: event.target.value } : row,
                    );
                    onChange({ ...draft, experience });
                  }}
                />
                <TextField
                  label="Начало"
                  type="date"
                  max={today}
                  value={item.start_date}
                  error={errors[`${prefix}.start_date`]}
                  onChange={(event) => {
                    const experience = draft.experience.map((row, i) =>
                      i === index ? { ...row, start_date: event.target.value } : row,
                    );
                    onChange({ ...draft, experience });
                  }}
                />
                <TextField
                  label="Окончание"
                  type="date"
                  max={today}
                  value={item.end_date}
                  disabled={item.is_current}
                  error={errors[`${prefix}.end_date`]}
                  onChange={(event) => {
                    const experience = draft.experience.map((row, i) =>
                      i === index ? { ...row, end_date: event.target.value } : row,
                    );
                    onChange({ ...draft, experience });
                  }}
                />
                <div className="md:col-span-2">
                  <Checkbox
                    label="По настоящее время"
                    checked={item.is_current}
                    onCheckedChange={(checked) => {
                      const experience = draft.experience.map((row, i) =>
                        i === index
                          ? { ...row, is_current: checked, end_date: checked ? "" : row.end_date }
                          : row,
                      );
                      onChange({ ...draft, experience });
                    }}
                  />
                </div>
                <TextArea
                  label="Описание"
                  value={item.description}
                  error={errors[`${prefix}.description`]}
                  rows={3}
                  containerClassName="md:col-span-2"
                  onChange={(event) => {
                    const experience = draft.experience.map((row, i) =>
                      i === index ? { ...row, description: event.target.value } : row,
                    );
                    onChange({ ...draft, experience });
                  }}
                />
                <TextArea
                  label="Достижения"
                  value={item.achievements}
                  error={errors[`${prefix}.achievements`]}
                  hint="Цифры, проценты, объём — быстрее поднимают оценку"
                  rows={3}
                  containerClassName="md:col-span-2"
                  onChange={(event) => {
                    const experience = draft.experience.map((row, i) =>
                      i === index ? { ...row, achievements: event.target.value } : row,
                    );
                    onChange({ ...draft, experience });
                  }}
                />
              </div>
            </div>
          );
        })}
        <Button
          variant="secondary"
          onClick={() => onChange({ ...draft, experience: [...draft.experience, emptyExperience()] })}
        >
          <Plus size={14} aria-hidden /> Добавить позицию
        </Button>
      </div>
    </Section>
  );
}

export function EducationSection({ draft, errors, onChange }: SectionProps) {
  return (
    <Section id="education" number="04" title="Образование">
      <div className="space-y-4">
        {draft.education.map((item, index) => {
          const prefix = `education.${index}`;
          return (
            <div key={item.key} className="rounded-lg border border-line bg-canvas p-4">
              <div className="mb-4 flex justify-end">
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-[13px] text-ink-muted hover:text-danger"
                  onClick={() =>
                    onChange({
                      ...draft,
                      education: draft.education.filter((_, i) => i !== index),
                    })
                  }
                >
                  <Trash2 size={13} aria-hidden /> Удалить
                </button>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <TextField
                  label="Учебное заведение"
                  value={item.institution}
                  error={errors[`${prefix}.institution`]}
                  containerClassName="md:col-span-2"
                  onChange={(event) => {
                    const education = draft.education.map((row, i) =>
                      i === index ? { ...row, institution: event.target.value } : row,
                    );
                    onChange({ ...draft, education });
                  }}
                />
                <TextField
                  label="Степень"
                  value={item.degree}
                  onChange={(event) => {
                    const education = draft.education.map((row, i) =>
                      i === index ? { ...row, degree: event.target.value } : row,
                    );
                    onChange({ ...draft, education });
                  }}
                />
                <TextField
                  label="Специальность"
                  value={item.field}
                  onChange={(event) => {
                    const education = draft.education.map((row, i) =>
                      i === index ? { ...row, field: event.target.value } : row,
                    );
                    onChange({ ...draft, education });
                  }}
                />
                <NumberField
                  label="Год начала"
                  value={item.start_year}
                  error={errors[`${prefix}.start_year`]}
                  onChange={(event) => {
                    const education = draft.education.map((row, i) =>
                      i === index ? { ...row, start_year: event.target.value } : row,
                    );
                    onChange({ ...draft, education });
                  }}
                />
                <NumberField
                  label="Год окончания"
                  value={item.end_year}
                  error={errors[`${prefix}.end_year`]}
                  onChange={(event) => {
                    const education = draft.education.map((row, i) =>
                      i === index ? { ...row, end_year: event.target.value } : row,
                    );
                    onChange({ ...draft, education });
                  }}
                />
              </div>
            </div>
          );
        })}
        <Button
          variant="secondary"
          onClick={() => onChange({ ...draft, education: [...draft.education, emptyEducation()] })}
        >
          <Plus size={14} aria-hidden /> Добавить образование
        </Button>
      </div>
    </Section>
  );
}

export function CoursesSection({ draft, errors, onChange }: SectionProps) {
  return (
    <Section id="courses" number="05" title="Курсы и сертификаты">
      <div className="space-y-4">
        {draft.courses.map((item, index) => {
          const prefix = `courses.${index}`;
          return (
            <div key={item.key} className="rounded-lg border border-line bg-canvas p-4">
              <div className="mb-4 flex justify-end">
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-[13px] text-ink-muted hover:text-danger"
                  onClick={() =>
                    onChange({
                      ...draft,
                      courses: draft.courses.filter((_, i) => i !== index),
                    })
                  }
                >
                  <Trash2 size={13} aria-hidden /> Удалить
                </button>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <TextField
                  label="Название"
                  value={item.title}
                  error={errors[`${prefix}.title`]}
                  containerClassName="md:col-span-2"
                  onChange={(event) => {
                    const courses = draft.courses.map((row, i) =>
                      i === index ? { ...row, title: event.target.value } : row,
                    );
                    onChange({ ...draft, courses });
                  }}
                />
                <TextField
                  label="Провайдер"
                  value={item.provider}
                  onChange={(event) => {
                    const courses = draft.courses.map((row, i) =>
                      i === index ? { ...row, provider: event.target.value } : row,
                    );
                    onChange({ ...draft, courses });
                  }}
                />
                <NumberField
                  label="Год"
                  value={item.year}
                  error={errors[`${prefix}.year`]}
                  onChange={(event) => {
                    const courses = draft.courses.map((row, i) =>
                      i === index ? { ...row, year: event.target.value } : row,
                    );
                    onChange({ ...draft, courses });
                  }}
                />
                <TextField
                  label="Ссылка на сертификат"
                  type="url"
                  value={item.certificate_url}
                  containerClassName="md:col-span-2"
                  onChange={(event) => {
                    const courses = draft.courses.map((row, i) =>
                      i === index ? { ...row, certificate_url: event.target.value } : row,
                    );
                    onChange({ ...draft, courses });
                  }}
                />
              </div>
            </div>
          );
        })}
        <Button
          variant="secondary"
          onClick={() => onChange({ ...draft, courses: [...draft.courses, emptyCourse()] })}
        >
          <Plus size={14} aria-hidden /> Добавить курс
        </Button>
      </div>
    </Section>
  );
}

export function SkillsSection({ draft, errors, onChange, suggestedSkills = [] }: SectionProps) {
  const existing = new Set(draft.skills.map((item) => item.skill.trim().toLocaleLowerCase("en")));
  const suggestions = suggestedSkills.filter(
    (skill) => skill && !existing.has(skill.toLocaleLowerCase("en")),
  );

  return (
    <Section
      id="skills"
      number="06"
      title="Навыки"
      hint="Добавляйте навыки, которыми готовы пользоваться в первой неделе работы."
    >
      <div className="space-y-3">
        {draft.skills.map((item, index) => {
          const prefix = `skills.${index}`;
          return (
            <div key={item.key} className="flex flex-wrap items-start gap-2">
              <TextField
                aria-label={`Навык ${index + 1}`}
                value={item.skill}
                error={errors[`${prefix}.skill`]}
                containerClassName="min-w-0 flex-1"
                onChange={(event) => {
                  const skills = draft.skills.map((row, i) =>
                    i === index ? { ...row, skill: event.target.value } : row,
                  );
                  onChange({ ...draft, skills });
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === ",") {
                    event.preventDefault();
                    if (item.skill.trim()) {
                      onChange({ ...draft, skills: [...draft.skills, emptySkill()] });
                    }
                  }
                }}
              />
              <div className="flex items-center gap-1 pt-1" role="group" aria-label={`Уровень навыка ${index + 1}`}>
                {[1, 2, 3, 4, 5].map((level) => {
                  const active = Number(item.level) >= level;
                  return (
                    <button
                      key={level}
                      type="button"
                      aria-label={`Уровень ${level}`}
                      aria-pressed={Number(item.level) === level}
                      className={
                        active
                          ? "h-3 w-3 rounded-full bg-accent"
                          : "h-3 w-3 rounded-full border border-line-strong bg-surface"
                      }
                      onClick={() => {
                        const skills = draft.skills.map((row, i) =>
                          i === index ? { ...row, level: String(level) } : row,
                        );
                        onChange({ ...draft, skills });
                      }}
                    />
                  );
                })}
              </div>
              {errors[`${prefix}.level`] && (
                <p className="w-full text-[13px] text-danger">{errors[`${prefix}.level`]}</p>
              )}
              <IconButton
                label="Удалить навык"
                onClick={() =>
                  onChange({
                    ...draft,
                    skills: draft.skills.filter((_, i) => i !== index),
                  })
                }
              >
                <X size={15} aria-hidden />
              </IconButton>
            </div>
          );
        })}
        <Button
          variant="ghost"
          onClick={() => onChange({ ...draft, skills: [...draft.skills, emptySkill()] })}
        >
          <Plus size={14} aria-hidden /> Добавить навык
        </Button>
        {suggestions.length > 0 && (
          <div className="pt-2">
            <p className="mb-2 text-[13px] text-ink-muted">Часто встречаются в похожих вакансиях:</p>
            <ul className="flex flex-wrap gap-2">
              {suggestions.slice(0, 8).map((skill) => (
                <li key={skill}>
                  <button type="button" onClick={() => onChange({ ...draft, skills: [...draft.skills, emptySkill(skill)] })}>
                    <Chip tone="muted">+ {skill}</Chip>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Section>
  );
}

export function LanguagesSection({ draft, errors, onChange }: SectionProps) {
  return (
    <Section id="languages" number="07" title="Языки">
      <div className="space-y-3">
        {draft.languages.map((item, index) => {
          const prefix = `languages.${index}`;
          return (
            <div key={item.key} className="flex flex-wrap items-start gap-2">
              <TextField
                label={index === 0 ? "Язык" : undefined}
                value={item.language}
                error={errors[`${prefix}.language`]}
                containerClassName="min-w-[160px] flex-1"
                onChange={(event) => {
                  const languages = draft.languages.map((row, i) =>
                    i === index ? { ...row, language: event.target.value } : row,
                  );
                  onChange({ ...draft, languages });
                }}
              />
              <Select
                label={index === 0 ? "Уровень" : undefined}
                value={item.level}
                error={errors[`${prefix}.level`]}
                containerClassName="w-[200px]"
                onChange={(event) => {
                  const languages = draft.languages.map((row, i) =>
                    i === index
                      ? { ...row, level: event.target.value as LanguageLevel | "" }
                      : row,
                  );
                  onChange({ ...draft, languages });
                }}
              >
                <option value="">Выберите</option>
                {LANGUAGE_OPTIONS.map((level) => (
                  <option key={level} value={level}>
                    {LANGUAGE_LEVEL_LABELS[level]}
                  </option>
                ))}
              </Select>
              <IconButton
                label="Удалить язык"
                className={index === 0 ? "mt-7" : "mt-1"}
                onClick={() =>
                  onChange({
                    ...draft,
                    languages: draft.languages.filter((_, i) => i !== index),
                  })
                }
              >
                <X size={15} aria-hidden />
              </IconButton>
            </div>
          );
        })}
        <Button
          variant="ghost"
          onClick={() => onChange({ ...draft, languages: [...draft.languages, emptyLanguage()] })}
        >
          <Plus size={14} aria-hidden /> Добавить язык
        </Button>
      </div>
    </Section>
  );
}
