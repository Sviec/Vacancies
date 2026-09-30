import { FileQuestion, Save, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "@/api/client";
import { useResume } from "@/api/resumes";
import type { ResumeRead } from "@/api/types";
import { parseScoreDetails } from "@/api/types";
import { useFiltersMeta } from "@/api/vacancies";
import { PageHeader } from "@/components/layout/AppShell";
import { Button, buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Checkbox, TextField } from "@/components/ui/fields";
import { Skeleton } from "@/components/ui/Skeleton";
import { validateDraft } from "@/features/editor/draft";
import { GenerateModal } from "@/features/editor/GenerateModal";
import { ScorePanel } from "@/features/editor/ScorePanel";
import {
  BasicsSection,
  CoursesSection,
  EducationSection,
  ExperienceSection,
  GoalsSection,
  LanguagesSection,
  SkillsSection,
} from "@/features/editor/sections";
import { useLocalDraft } from "@/features/editor/use-local-draft";
import { saveStatusLabel, useSaveResume } from "@/features/editor/use-save-resume";
import { cn } from "@/lib/cn";

export function ResumeEditorPage() {
  const { resumeId = "" } = useParams();
  const query = useResume(resumeId);
  const meta = useFiltersMeta();

  if (query.isPending) {
    return <EditorSkeleton />;
  }

  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    if (notFound) {
      return (
        <>
          <PageHeader eyebrow="Редактор" title="Редактор резюме" />
          <EmptyState
            icon={FileQuestion}
            title="Резюме не найдено"
            description="Возможно, его удалили или ссылка устарела."
            action={
              <Link to="/resumes" className={cn(buttonClasses("primary", "md"))}>
                К списку резюме
              </Link>
            }
          />
        </>
      );
    }
    return (
      <>
        <PageHeader eyebrow="Редактор" title="Редактор резюме" />
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </>
    );
  }

  return (
    <ResumeEditorLoaded
      key={query.data.id}
      resume={query.data}
      countries={meta.data?.countries ?? []}
      cities={meta.data?.cities ?? []}
    />
  );
}

function ResumeEditorLoaded({
  resume,
  countries,
  cities,
}: {
  resume: ResumeRead;
  countries: string[];
  cities: string[];
}) {
  const local = useLocalDraft(resume);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [aiOpen, setAiOpen] = useState(false);
  const todayIso = useMemo(() => new Date().toISOString().slice(0, 10), []);

  const save = useSaveResume({
    resume,
    draft: local.draft,
    setFieldErrors,
    onSaved: local.rehydrateFromResume,
  });

  const draft = local.draft;
  const suggestedSkills = parseScoreDetails(resume.score_details)?.market.top_skills ?? [];

  const onChange = (next: typeof draft) => {
    local.setDraft(next);
    if (Object.keys(fieldErrors).length > 0) {
      setFieldErrors(validateDraft(next, new Date()));
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Работа над собой"
        title="Редактор резюме"
        description="Соберите версию, которая говорит о вашем опыте ясно. Оценка обновляется после сохранения на сервер."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" onClick={() => setAiOpen(true)}>
              <Sparkles size={15} aria-hidden /> Сгенерировать через ИИ
            </Button>
            <Button variant="primary" disabled={!save.dirty || save.saving} onClick={save.save}>
              <Save size={15} aria-hidden /> Сохранить
            </Button>
          </div>
        }
      />

      {local.banner && (
        <div
          role="status"
          className="mb-6 rounded-card border border-accent-border bg-accent-soft px-4 py-4"
        >
          <p className="text-[14px] font-medium text-ink">Восстановлены несохранённые изменения</p>
          {local.banner.stale && (
            <p className="mt-1 text-[13px] leading-5 text-warn">
              Резюме изменилось с момента начала правок — сохранение черновика перезапишет серверную
              версию.
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="primary" onClick={local.continueDraft}>
              Продолжить
            </Button>
            <Button size="sm" variant="ghost" onClick={local.discardDraft}>
              Отбросить
            </Button>
          </div>
        </div>
      )}

      <div className="mb-5 flex flex-wrap items-center gap-4">
        <TextField
          label="Название резюме"
          value={draft.title}
          error={fieldErrors.title}
          containerClassName="min-w-[220px] flex-1"
          onChange={(event) => onChange({ ...draft, title: event.target.value })}
        />
        <Checkbox
          label="Основное"
          checked={draft.is_primary}
          onCheckedChange={(checked) => onChange({ ...draft, is_primary: checked })}
        />
        <p aria-live="polite" className="text-[13px] text-ink-muted">
          {saveStatusLabel(save.status)}
          {save.status === "error" && (
            <>
              {" — "}
              <button
                type="button"
                className="font-medium text-accent hover:text-accent-hover"
                onClick={save.retry}
              >
                Повторить
              </button>
            </>
          )}
        </p>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="order-2 min-w-0 space-y-4 lg:order-1">
          <BasicsSection draft={draft} errors={fieldErrors} today={todayIso} onChange={onChange} />
          <GoalsSection
            draft={draft}
            errors={fieldErrors}
            today={todayIso}
            onChange={onChange}
            countries={countries}
            cities={cities}
          />
          <ExperienceSection
            draft={draft}
            errors={fieldErrors}
            today={todayIso}
            onChange={onChange}
          />
          <EducationSection
            draft={draft}
            errors={fieldErrors}
            today={todayIso}
            onChange={onChange}
          />
          <CoursesSection draft={draft} errors={fieldErrors} today={todayIso} onChange={onChange} />
          <SkillsSection
            draft={draft}
            errors={fieldErrors}
            today={todayIso}
            onChange={onChange}
            suggestedSkills={suggestedSkills}
          />
          <LanguagesSection
            draft={draft}
            errors={fieldErrors}
            today={todayIso}
            onChange={onChange}
          />
        </div>
        <div className="order-1 lg:order-2">
          <ScorePanel resume={resume} dirty={save.dirty} saving={save.saving} />
        </div>
      </div>

      <GenerateModal open={aiOpen} onClose={() => setAiOpen(false)} />
    </>
  );
}

function EditorSkeleton() {
  return (
    <div aria-busy="true" aria-label="Загрузка редактора">
      <Skeleton className="mb-3 h-4 w-40" />
      <Skeleton className="mb-2 h-9 w-72" />
      <Skeleton className="mb-8 h-4 w-96" />
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          {Array.from({ length: 3 }, (_, index) => (
            <div key={index} className="rounded-card border border-line bg-surface p-5">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="mt-4 h-9 w-full" />
              <Skeleton className="mt-3 h-9 w-full" />
              <Skeleton className="mt-3 h-24 w-full" />
            </div>
          ))}
        </div>
        <div className="rounded-card border border-line bg-surface p-5">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="mt-4 h-[118px] w-[118px] rounded-full" />
          <Skeleton className="mt-5 h-[200px] w-full" />
        </div>
      </div>
    </div>
  );
}
