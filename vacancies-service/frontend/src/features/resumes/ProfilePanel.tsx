import { Plus, Trash2, UserRound } from "lucide-react";
import { useRef } from "react";

import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";
import { Select, TextField } from "@/components/ui/fields";
import { emptyEducation, emptyLanguage } from "@/features/editor/draft";
import type { ProfileForm } from "@/features/resumes/profile";
import { LANGUAGE_LEVEL_LABELS } from "@/lib/labels";
import type { LanguageLevel } from "@/api/types";

const CONTACT_FIELDS = [
  { key: "email", label: "Email", type: "email" as const },
  { key: "phone", label: "Телефон", type: "tel" as const },
  { key: "telegram", label: "Telegram", type: "text" as const },
  { key: "linkedin", label: "LinkedIn", type: "url" as const },
  { key: "github", label: "GitHub", type: "url" as const },
  { key: "website", label: "Сайт", type: "url" as const },
] as const;

const LANGUAGE_OPTIONS = Object.keys(LANGUAGE_LEVEL_LABELS) as LanguageLevel[];
const PHOTO_LIMIT = 1_500_000;

interface ProfilePanelProps {
  form: ProfileForm;
  errors: Record<string, string>;
  photo: string | null;
  saving: boolean;
  onChange: (next: ProfileForm) => void;
  onPhoto: (dataUrl: string | null) => void;
  onPhotoError: (message: string) => void;
  onSave: () => void;
}

/** Боковая карточка общих данных. Сохранение переносит их во все резюме. */
export function ProfilePanel({
  form,
  errors,
  photo,
  saving,
  onChange,
  onPhoto,
  onPhotoError,
  onSave,
}: ProfilePanelProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  const onFile = (file: File | undefined) => {
    if (!file) {
      return;
    }
    if (!file.type.startsWith("image/") || file.size > PHOTO_LIMIT) {
      onPhotoError("Нужна картинка легче 1,5 МБ");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const value = typeof reader.result === "string" ? reader.result : "";
      if (!value.startsWith("data:image/")) {
        onPhotoError("Не удалось прочитать файл");
        return;
      }
      onPhoto(value);
    };
    reader.readAsDataURL(file);
  };

  return (
    <aside className="rounded-card border border-line bg-surface p-5 shadow-card lg:sticky lg:top-24 lg:max-h-[calc(100dvh-7rem)] lg:overflow-y-auto">
      <h2 className="text-[15px] font-semibold text-ink">Общие данные</h2>
      <p className="mt-1 text-[13px] leading-5 text-ink-muted">
        Фото, контакты, место жительства, образование и языки одни на все резюме. После сохранения
        они записываются в каждую версию.
      </p>

      <div className="mt-5 flex items-center gap-4">
        <span className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-full bg-accent-soft text-accent">
          {photo ? (
            <img src={photo} alt="" className="h-full w-full object-cover" />
          ) : (
            <UserRound size={28} strokeWidth={1.6} aria-hidden />
          )}
        </span>
        <div className="flex flex-col gap-2">
          <Button type="button" size="sm" variant="secondary" onClick={() => fileRef.current?.click()}>
            {photo ? "Заменить фото" : "Загрузить фото"}
          </Button>
          {photo && (
            <button
              type="button"
              className="text-left text-[13px] text-ink-muted hover:text-danger"
              onClick={() => onPhoto(null)}
            >
              Убрать
            </button>
          )}
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="sr-only"
            onChange={(event) => {
              onFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </div>
      </div>

      <div className="mt-5 space-y-4">
        <p className="text-[13px] font-medium text-ink">Контакты</p>
        {CONTACT_FIELDS.map((field) => (
          <TextField
            key={field.key}
            label={field.label}
            type={field.type}
            value={form.contacts[field.key]}
            error={errors[`contacts.${field.key}`]}
            onChange={(event) =>
              onChange({
                ...form,
                contacts: { ...form.contacts, [field.key]: event.target.value },
              })
            }
          />
        ))}
      </div>

      <div className="mt-5 space-y-4">
        <p className="text-[13px] font-medium text-ink">Место жительства</p>
        <TextField
          label="Страна"
          value={form.country}
          error={errors.desired_country}
          onChange={(event) => onChange({ ...form, country: event.target.value })}
        />
        <TextField
          label="Город"
          value={form.city}
          error={errors.desired_city}
          onChange={(event) => onChange({ ...form, city: event.target.value })}
        />
      </div>

      <div className="mt-5 space-y-3">
        <p className="text-[13px] font-medium text-ink">Образование</p>
        {form.education.map((item, index) => {
          const prefix = `education.${index}`;
          return (
            <div key={item.key} className="rounded-lg border border-line bg-canvas p-4">
              <div className="mb-3 flex justify-end">
                <IconButton
                  label="Удалить образование"
                  onClick={() =>
                    onChange({
                      ...form,
                      education: form.education.filter((_, i) => i !== index),
                    })
                  }
                >
                  <Trash2 size={14} aria-hidden />
                </IconButton>
              </div>
              <div className="space-y-3">
                <TextField
                  label="Учебное заведение"
                  value={item.institution}
                  error={errors[`${prefix}.institution`]}
                  onChange={(event) =>
                    onChange({
                      ...form,
                      education: form.education.map((row, i) =>
                        i === index ? { ...row, institution: event.target.value } : row,
                      ),
                    })
                  }
                />
                <TextField
                  label="Степень"
                  value={item.degree}
                  error={errors[`${prefix}.degree`]}
                  onChange={(event) =>
                    onChange({
                      ...form,
                      education: form.education.map((row, i) =>
                        i === index ? { ...row, degree: event.target.value } : row,
                      ),
                    })
                  }
                />
                <TextField
                  label="Специальность"
                  value={item.field}
                  error={errors[`${prefix}.field`]}
                  onChange={(event) =>
                    onChange({
                      ...form,
                      education: form.education.map((row, i) =>
                        i === index ? { ...row, field: event.target.value } : row,
                      ),
                    })
                  }
                />
              </div>
            </div>
          );
        })}
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => onChange({ ...form, education: [...form.education, emptyEducation()] })}
        >
          <Plus size={14} aria-hidden /> Добавить образование
        </Button>
      </div>

      <div className="mt-5 space-y-3">
        <p className="text-[13px] font-medium text-ink">Языки</p>
        {form.languages.map((item, index) => {
          const prefix = `languages.${index}`;
          return (
            <div key={item.key} className="flex items-start gap-2">
              <TextField
                label="Язык"
                value={item.language}
                error={errors[`${prefix}.language`]}
                containerClassName="min-w-0 flex-1"
                onChange={(event) =>
                  onChange({
                    ...form,
                    languages: form.languages.map((row, i) =>
                      i === index ? { ...row, language: event.target.value } : row,
                    ),
                  })
                }
              />
              <Select
                label="Уровень"
                value={item.level}
                error={errors[`${prefix}.level`]}
                containerClassName="w-36 shrink-0"
                onChange={(event) =>
                  onChange({
                    ...form,
                    languages: form.languages.map((row, i) =>
                      i === index ? { ...row, level: event.target.value as LanguageLevel | "" } : row,
                    ),
                  })
                }
              >
                <option value="">—</option>
                {LANGUAGE_OPTIONS.map((level) => (
                  <option key={level} value={level}>
                    {LANGUAGE_LEVEL_LABELS[level]}
                  </option>
                ))}
              </Select>
              <IconButton
                label="Удалить язык"
                className="mt-6"
                onClick={() =>
                  onChange({
                    ...form,
                    languages: form.languages.filter((_, i) => i !== index),
                  })
                }
              >
                <Trash2 size={14} aria-hidden />
              </IconButton>
            </div>
          );
        })}
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => onChange({ ...form, languages: [...form.languages, emptyLanguage()] })}
        >
          <Plus size={14} aria-hidden /> Добавить язык
        </Button>
      </div>

      <Button type="button" variant="primary" className="mt-5 w-full" disabled={saving} onClick={onSave}>
        {saving ? "Сохранение…" : "Сохранить в резюме"}
      </Button>
    </aside>
  );
}
