import { motion } from "framer-motion";
import { FileText, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router";

import { ApiError } from "@/api/client";
import {
  useCreateResume,
  useDeleteResume,
  useDuplicateResume,
  useResume,
  useResumeDetails,
  useResumes,
  useUpdateResume,
} from "@/api/resumes";
import type { ResumeCreate, ResumeListItem, ResumeRead } from "@/api/types";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toaster";
import { ProfilePanel } from "@/features/resumes/ProfilePanel";
import { ResumeCard } from "@/features/resumes/ResumeCard";
import type { ProfileForm } from "@/features/resumes/profile";
import {
  clearProfilePhoto,
  emptyProfile,
  mergeProfileIntoStoredDrafts,
  profileFromResume,
  profileToUpdate,
  readProfilePhoto,
  validateProfile,
  writeProfilePhoto,
} from "@/features/resumes/profile";
import { rise, useReducedMotionSafe } from "@/lib/motion";
import { pluralRu } from "@/lib/format";

export function ResumesPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const reduced = useReducedMotionSafe();
  const now = useMemo(() => new Date(), []);
  const query = useResumes();
  const create = useCreateResume();
  const duplicate = useDuplicateResume();
  const update = useUpdateResume();
  const remove = useDeleteResume();

  const items = query.data?.items ?? [];
  const primary = items.find((item) => item.is_primary) ?? items[0];
  const primaryQuery = useResume(primary?.id ?? "");
  const details = useResumeDetails(items.map((item) => item.id));
  const detailById = new Map<string, ResumeRead>();
  items.forEach((item, index) => {
    const data = details[index]?.data;
    if (data) {
      detailById.set(item.id, data);
    }
  });

  const [edited, setEdited] = useState<ProfileForm | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [photo, setPhoto] = useState<string | null>(() => readProfilePhoto());
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ResumeListItem | null>(null);
  const form = edited ?? (primaryQuery.data ? profileFromResume(primaryQuery.data) : emptyProfile());

  const busyId =
    duplicate.isPending || update.isPending || remove.isPending
      ? (duplicate.variables ??
        (update.variables as { id?: string } | undefined)?.id ??
        remove.variables ??
        null)
      : null;

  const changeForm = (next: ProfileForm) => {
    setEdited(next);
  };

  const createBlank = () => {
    const profileErrors = validateProfile(form, new Date());
    const shared = Object.keys(profileErrors).length === 0 ? profileToUpdate(form) : {};
    const body: ResumeCreate = {
      title: "Новое резюме",
      is_primary: items.length === 0,
      contacts: shared.contacts ?? undefined,
      education: shared.education ?? undefined,
      languages: shared.languages ?? undefined,
      desired_city: shared.desired_city,
      desired_country: shared.desired_country,
    };
    create.mutate(
      body,
      {
        onSuccess: (resume) => {
          toast({
            message:
              Object.keys(profileErrors).length === 0
                ? "Резюме создано с данными профиля"
                : "Резюме создано. Общие данные не перенесены — в профиле есть ошибки",
          });
          void navigate(`/resumes/${resume.id}`);
        },
        onError: (error) => {
          toast({
            message: error instanceof ApiError ? error.message : "Не удалось создать резюме",
            tone: "danger",
          });
        },
      },
    );
  };

  const saveProfile = async () => {
    const nextErrors = validateProfile(form, new Date());
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      toast({ message: "Исправьте ошибки в профиле", tone: "danger" });
      return;
    }
    if (items.length === 0) {
      toast({ message: "Сначала создайте резюме — профиль записывается в него" });
      return;
    }
    setSaving(true);
    try {
      const body = profileToUpdate(form);
      for (const item of items) {
        await update.mutateAsync({ id: item.id, body });
      }
      mergeProfileIntoStoredDrafts(
        items.map((item) => item.id),
        form,
      );
      setEdited(null);
      toast({ message: "Профиль записан во все резюме" });
    } catch (error) {
      toast({
        message: error instanceof ApiError ? error.message : "Не удалось сохранить профиль",
        tone: "danger",
      });
    } finally {
      setSaving(false);
    }
  };

  let panel: ReactNode;
  if (primary && primaryQuery.isPending) {
    panel = <ProfileSkeleton />;
  } else if (primary && primaryQuery.isError) {
    panel = (
      <ErrorState
        error={primaryQuery.error}
        title="Не удалось загрузить профиль"
        onRetry={() => void primaryQuery.refetch()}
        retrying={primaryQuery.isFetching}
      />
    );
  } else {
    panel = (
      <ProfilePanel
        form={form}
        errors={errors}
        photo={photo}
        saving={saving}
        onChange={changeForm}
        onPhoto={(dataUrl) => {
          if (dataUrl) {
            writeProfilePhoto(dataUrl);
            setPhoto(dataUrl);
          } else {
            clearProfilePhoto();
            setPhoto(null);
          }
        }}
        onPhotoError={(message) => toast({ message, tone: "danger" })}
        onSave={() => void saveProfile()}
      />
    );
  }

  let list: ReactNode;
  if (items.length === 0) {
    list = (
      <EmptyState
        icon={FileText}
        title="Создайте первое резюме"
        description="Общие данные слева перенесутся в него при создании, если в профиле нет ошибок."
        action={
          <Button variant="primary" onClick={createBlank} disabled={create.isPending}>
            <Plus size={16} aria-hidden /> Новое резюме
          </Button>
        }
      />
    );
  } else {
    list = (
      <>
        <div className="mb-4 flex items-center justify-between gap-3">
          <p className="text-[13px] text-ink-muted">
            {items.length} {pluralRu(items.length, ["резюме", "резюме", "резюме"])}
          </p>
          <Button variant="secondary" size="sm" onClick={createBlank} disabled={create.isPending}>
            <Plus size={14} aria-hidden /> Новое резюме
          </Button>
        </div>
        <ul className="flex flex-col gap-3">
          {items.map((resume, index) => (
            <motion.li key={resume.id} {...rise(index, reduced)}>
              <ResumeCard
                resume={resume}
                detail={detailById.get(resume.id)}
                photo={photo}
                now={now}
                busy={busyId === resume.id}
                onDuplicate={() => {
                  duplicate.mutate(resume.id, {
                    onSuccess: () => toast({ message: "Резюме скопировано" }),
                    onError: (error) =>
                      toast({
                        message:
                          error instanceof ApiError ? error.message : "Не удалось скопировать",
                        tone: "danger",
                      }),
                  });
                }}
                onMakePrimary={() => {
                  update.mutate(
                    { id: resume.id, body: { is_primary: true } },
                    {
                      onSuccess: () => toast({ message: "Основное резюме обновлено" }),
                      onError: (error) =>
                        toast({
                          message:
                            error instanceof ApiError ? error.message : "Не удалось обновить",
                          tone: "danger",
                        }),
                    },
                  );
                }}
                onDelete={() => setDeleteTarget(resume)}
              />
            </motion.li>
          ))}
        </ul>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Ваши материалы"
        title="Профиль"
        description="Общие данные слева одни на все версии. Справа — резюме под разные роли: в превью видны опыт, навыки и оценка."
      />
      <div className="grid items-start gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        {query.isPending ? (
          <>
            <ProfileSkeleton />
            <ResumesSkeleton />
          </>
        ) : query.isError ? (
          <ErrorState
            className="lg:col-span-2"
            error={query.error}
            onRetry={() => void query.refetch()}
            retrying={query.isFetching}
          />
        ) : (
          <>
            {panel}
            <div className="min-w-0">{list}</div>
          </>
        )}
      </div>
      <ConfirmDialog
        open={deleteTarget !== null}
        title="Удалить резюме?"
        description={
          deleteTarget?.is_primary
            ? "Это основное резюме — основным станет самое свежее из оставшихся. Общие данные профиля останутся."
            : `«${deleteTarget?.title ?? ""}» будет удалено без возможности восстановления.`
        }
        confirmLabel="Удалить"
        tone="danger"
        pending={remove.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) {
            return;
          }
          remove.mutate(deleteTarget.id, {
            onSuccess: () => {
              toast({ message: "Резюме удалено" });
              setDeleteTarget(null);
            },
            onError: (error) =>
              toast({
                message: error instanceof ApiError ? error.message : "Не удалось удалить",
                tone: "danger",
              }),
          });
        }}
      />
    </>
  );
}

function ProfileSkeleton() {
  return (
    <div aria-busy="true" aria-label="Загрузка профиля" className="rounded-card border border-line bg-surface p-5 shadow-card">
      <Skeleton className="h-5 w-2/5" />
      <Skeleton className="mt-3 h-4 w-full" />
      <Skeleton className="mt-2 h-4 w-4/5" />
      <div className="mt-5 flex items-center gap-4">
        <Skeleton className="h-16 w-16 rounded-full" />
        <Skeleton className="h-8 w-32" />
      </div>
      <Skeleton className="mt-5 h-4 w-1/3" />
      <Skeleton className="mt-3 h-9 w-full" />
      <Skeleton className="mt-3 h-9 w-full" />
      <Skeleton className="mt-3 h-9 w-full" />
    </div>
  );
}

function ResumesSkeleton() {
  return (
    <ul aria-busy="true" aria-label="Загрузка резюме" className="flex flex-col gap-3">
      {Array.from({ length: 3 }, (_, index) => (
        <li key={index} className="flex gap-4 rounded-card border border-line bg-surface p-5 shadow-card">
          <Skeleton className="h-12 w-12 rounded-full" />
          <div className="min-w-0 flex-1">
            <Skeleton className="h-5 w-2/5" />
            <Skeleton className="mt-2 h-4 w-1/3" />
            <Skeleton className="mt-3 h-4 w-4/5" />
            <Skeleton className="mt-2 h-4 w-3/5" />
          </div>
        </li>
      ))}
    </ul>
  );
}
