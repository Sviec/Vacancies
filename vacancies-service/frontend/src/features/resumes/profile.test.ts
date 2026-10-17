import { describe, expect, it } from "vitest";

import type { ResumeDraft } from "@/features/editor/draft";
import { applyProfileToDraft, profileToUpdate, validateProfile } from "@/features/resumes/profile";
import type { ProfileForm } from "@/features/resumes/profile";

function form(overrides: Partial<ProfileForm> = {}): ProfileForm {
  return {
    contacts: {
      email: "a@b.c",
      phone: "",
      telegram: "",
      linkedin: "",
      github: "",
      website: "",
    },
    country: "Россия",
    city: "Москва",
    education: [],
    languages: [],
    ...overrides,
  };
}

describe("profileToUpdate", () => {
  it("кладёт контакты и место жительства в поля резюме", () => {
    const update = profileToUpdate(form());
    expect(update.contacts?.email).toBe("a@b.c");
    expect(update.desired_city).toBe("Москва");
    expect(update.desired_country).toBe("Россия");
    expect(update.education).toEqual([]);
  });

  it("отбрасывает пустую строку образования", () => {
    const update = profileToUpdate(
      form({
        education: [
          {
            key: "1",
            institution: "",
            degree: "",
            field: "",
            start_year: "",
            end_year: "",
          },
        ],
      }),
    );
    expect(update.education).toEqual([]);
  });
});

describe("validateProfile", () => {
  it("просит уровень, если язык указан", () => {
    const errors = validateProfile(
      form({ languages: [{ key: "1", language: "English", level: "" }] }),
      new Date("2026-10-03T00:00:00Z"),
    );
    expect(errors["languages.0.level"]).toBeTruthy();
  });
});

describe("applyProfileToDraft", () => {
  it("заменяет общие поля и не трогает опыт", () => {
    const draft = {
      title: "Версия",
      target_position: "Analyst",
      experience: [{ key: "e", company: "Acme", position: "Dev" }],
      contacts: { email: "old@b.c", phone: "", telegram: "", linkedin: "", github: "", website: "" },
      desired_city: "",
      desired_country: "",
      education: [],
      languages: [],
    } as unknown as ResumeDraft;
    const next = applyProfileToDraft(draft, form());
    expect(next.title).toBe("Версия");
    expect(next.experience).toEqual(draft.experience);
    expect(next.contacts.email).toBe("a@b.c");
    expect(next.desired_city).toBe("Москва");
  });
});
