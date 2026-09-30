import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";
import type { ResumeRead } from "@/api/types";
import {
  diffPayload,
  draftMatchesResume,
  fromResume,
  mapServerErrors,
  toPayload,
  validateDraft,
} from "@/features/editor/draft";

/** Фикстура по мотивам strong из app/data/demo_resumes.json. */
function strongResume(overrides: Partial<ResumeRead> = {}): ResumeRead {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    user_id: "00000000-0000-0000-0000-000000000001",
    title: "Senior Python Developer",
    is_primary: true,
    origin: "manual",
    target_position: "Senior Python Developer",
    desired_salary_min: 400000,
    desired_salary_currency: "RUB",
    desired_country: "Россия",
    desired_city: "Москва",
    desired_work_format: "hybrid",
    summary:
      "Бэкенд-разработчик с восьмилетним опытом: высоконагруженные сервисы на Python.",
    contacts: {
      email: "strong.dev@example.com",
      telegram: "@strong_dev",
      github: "https://github.com/strong-dev",
      phone: null,
      linkedin: null,
      website: null,
    },
    score: 9.2,
    score_details: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    experience: [
      {
        id: "22222222-2222-2222-2222-222222222221",
        company: "Яндекс",
        position: "Ведущий Python-разработчик",
        start_date: "2022-04-01",
        end_date: null,
        is_current: true,
        description: "Отвечаю за бэкенд сервиса рекомендаций.",
        achievements: "Сократил p95 задержки ответа с 450 до 120 мс.",
      },
      {
        id: "22222222-2222-2222-2222-222222222222",
        company: "Ozon",
        position: "Python-разработчик",
        start_date: "2019-09-01",
        end_date: "2022-04-01",
        is_current: false,
        description: "Разрабатывал микросервисы каталога.",
        achievements: "Ускорил импорт прайс-листов в 4 раза.",
      },
    ],
    education: [
      {
        id: "33333333-3333-3333-3333-333333333331",
        institution: "МГТУ им. Н. Э. Баумана",
        degree: "Бакалавр",
        field: "Программная инженерия",
        start_year: 2013,
        end_year: 2017,
      },
    ],
    skills: [
      { id: "44444444-4444-4444-4444-444444444441", skill: "python", level: 5 },
      { id: "44444444-4444-4444-4444-444444444442", skill: "fastapi", level: 5 },
      { id: "44444444-4444-4444-4444-444444444443", skill: "postgresql", level: 4 },
    ],
    courses: [
      {
        id: "55555555-5555-5555-5555-555555555551",
        title: "Kubernetes для разработчиков",
        provider: "Slurm",
        year: 2023,
        certificate_url: null,
      },
    ],
    languages: [
      { id: "66666666-6666-6666-6666-666666666661", language: "Русский", level: "native" },
      { id: "66666666-6666-6666-6666-666666666662", language: "English", level: "C1" },
    ],
    ...overrides,
  };
}

const TODAY = new Date("2026-09-30T12:00:00Z");

describe("fromResume / toPayload", () => {
  it("туда-обратно сохраняет поля strong", () => {
    const resume = strongResume();
    const draft = fromResume(resume);
    const payload = toPayload(draft);

    expect(payload.title).toBe("Senior Python Developer");
    expect(payload.is_primary).toBe(true);
    expect(payload.target_position).toBe("Senior Python Developer");
    expect(payload.desired_salary_min).toBe(400000);
    expect(payload.desired_salary_currency).toBe("RUB");
    expect(payload.desired_work_format).toBe("hybrid");
    expect(payload.contacts?.email).toBe("strong.dev@example.com");
    expect(payload.contacts?.phone).toBeNull();
    expect(payload.experience).toHaveLength(2);
    expect(payload.experience?.[0]).toMatchObject({
      company: "Яндекс",
      is_current: true,
      end_date: null,
      start_date: "2022-04-01",
    });
    expect(payload.education?.[0]).toMatchObject({
      institution: "МГТУ им. Н. Э. Баумана",
      start_year: 2013,
      end_year: 2017,
    });
    expect(payload.skills).toEqual([
      { skill: "python", level: 5 },
      { skill: "fastapi", level: 5 },
      { skill: "postgresql", level: 4 },
    ]);
    expect(payload.languages).toEqual([
      { language: "Русский", level: "native" },
      { language: "English", level: "C1" },
    ]);
    expect(draftMatchesResume(draft, resume)).toBe(true);
  });

  it("пустые строки → null, числа парсятся", () => {
    const draft = fromResume(strongResume());
    draft.target_position = "  ";
    draft.desired_salary_min = "250000";
    draft.summary = "";
    const payload = toPayload(draft);
    expect(payload.target_position).toBeNull();
    expect(payload.desired_salary_min).toBe(250000);
    expect(payload.summary).toBeNull();
  });
});

describe("diffPayload", () => {
  it("возвращает только изменившиеся ключи верхнего уровня", () => {
    const a = toPayload(fromResume(strongResume()));
    const b = { ...a, title: "Новое название", summary: a.summary };
    const diff = diffPayload(a, b);
    expect(Object.keys(diff)).toEqual(["title"]);
    expect(diff.title).toBe("Новое название");
  });

  it("секции уходят целиком при любом изменении списка", () => {
    const a = toPayload(fromResume(strongResume()));
    const skills = [...(a.skills ?? []), { skill: "redis", level: 3 }];
    const b = { ...a, skills };
    const diff = diffPayload(a, b);
    expect(diff.skills).toEqual(skills);
    expect(diff.title).toBeUndefined();
  });
});

describe("draftMatchesResume / восстановление", () => {
  it("черновик равен серверу → не восстанавливать", () => {
    const resume = strongResume();
    expect(draftMatchesResume(fromResume(resume), resume)).toBe(true);
  });

  it("изменённый черновик отличается от сервера", () => {
    const resume = strongResume();
    const draft = fromResume(resume);
    draft.skills.push({ key: "x", skill: "graphql", level: "3" });
    expect(draftMatchesResume(draft, resume)).toBe(false);
  });
});

describe("validateDraft", () => {
  it("принимает валидный strong", () => {
    expect(validateDraft(fromResume(strongResume()), TODAY)).toEqual({});
  });

  it("title обязателен и до 255", () => {
    const draft = fromResume(strongResume());
    draft.title = "";
    expect(validateDraft(draft, TODAY).title).toBeTruthy();
    draft.title = "x".repeat(256);
    expect(validateDraft(draft, TODAY).title).toMatch(/255/);
  });

  it("company и position обязательны", () => {
    const draft = fromResume(strongResume());
    draft.experience[0].company = "";
    draft.experience[0].position = "";
    const errors = validateDraft(draft, TODAY);
    expect(errors["experience.0.company"]).toBeTruthy();
    expect(errors["experience.0.position"]).toBeTruthy();
  });

  it("даты не в будущем, end > start, is_current очищает end", () => {
    const draft = fromResume(strongResume());
    draft.experience[0].is_current = false;
    draft.experience[0].start_date = "2026-10-01";
    draft.experience[0].end_date = "2026-09-01";
    let errors = validateDraft(draft, TODAY);
    expect(errors["experience.0.start_date"]).toBeTruthy();

    draft.experience[0].start_date = "2020-01-01";
    draft.experience[0].end_date = "2019-01-01";
    errors = validateDraft(draft, TODAY);
    expect(errors["experience.0.end_date"]).toBeTruthy();

    draft.experience[0].is_current = true;
    draft.experience[0].end_date = "2024-01-01";
    errors = validateDraft(draft, TODAY);
    expect(errors["experience.0.end_date"]).toBeTruthy();
  });

  it("годы образования и end_year ≥ start_year", () => {
    const draft = fromResume(strongResume());
    draft.education[0].start_year = "2018";
    draft.education[0].end_year = "2015";
    expect(validateDraft(draft, TODAY)["education.0.end_year"]).toBeTruthy();
    draft.education[0].start_year = "1800";
    expect(validateDraft(draft, TODAY)["education.0.start_year"]).toBeTruthy();
  });

  it("institution и course title обязательны", () => {
    const draft = fromResume(strongResume());
    draft.education[0].institution = "";
    draft.courses[0].title = "";
    const errors = validateDraft(draft, TODAY);
    expect(errors["education.0.institution"]).toBeTruthy();
    expect(errors["courses.0.title"]).toBeTruthy();
  });

  it("skill level 1–5 и уникальность без учёта регистра", () => {
    const draft = fromResume(strongResume());
    draft.skills[0].level = "9";
    expect(validateDraft(draft, TODAY)["skills.0.level"]).toBeTruthy();
    draft.skills[0].level = "5";
    draft.skills.push({ key: "d", skill: "Python", level: "3" });
    expect(validateDraft(draft, TODAY)["skills.3.skill"]).toBeTruthy();
  });

  it("язык уникален, уровень из enum", () => {
    const draft = fromResume(strongResume());
    draft.languages.push({ key: "d", language: "english", level: "B1" });
    expect(validateDraft(draft, TODAY)["languages.2.language"]).toBeTruthy();
    draft.languages.pop();
    draft.languages[1].level = "" as never;
    expect(validateDraft(draft, TODAY)["languages.1.level"]).toBeTruthy();
  });

  it("зарплата ≥0, валюта A–Z×3", () => {
    const draft = fromResume(strongResume());
    draft.desired_salary_min = "-1";
    expect(validateDraft(draft, TODAY).desired_salary_min).toBeTruthy();
    draft.desired_salary_min = "100";
    draft.desired_salary_currency = "rub";
    expect(validateDraft(draft, TODAY).desired_salary_currency).toBeTruthy();
  });
});

describe("mapServerErrors", () => {
  it("превращает loc body/experience/0/end_date в путь", () => {
    const error = new ApiError("VALIDATION_ERROR", "fail", 422, {
      errors: [
        {
          loc: ["body", "experience", 0, "end_date"],
          msg: "end_date must be greater than start_date",
          type: "value_error",
        },
        {
          loc: ["body", "title"],
          msg: "String should have at least 1 character",
          type: "string_too_short",
        },
      ],
    });
    expect(mapServerErrors(error)).toEqual({
      "experience.0.end_date": "end_date must be greater than start_date",
      title: "String should have at least 1 character",
    });
  });
});
