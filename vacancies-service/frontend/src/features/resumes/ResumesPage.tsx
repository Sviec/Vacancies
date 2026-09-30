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
  useResumes,
  useUpdateResume,
} from "@/api/resumes";
import type { ResumeListItem } from "@/api/types";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toaster";
import { ResumeCard } from "@/features/resumes/ResumeCard";
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

  const [deleteTarget, setDeleteTarget] = useState<ResumeListItem | null>(null);
  const busyId =
    duplicate.isPending || update.isPending || remove.isPending
      ? (duplicate.variables ??
        (update.variables as { id?: string } | undefined)?.id ??
        remove.variables ??
        null)
      : null;

  const createBlank = () => {
    create.mutate(
      { title: "Новое резюме", is_primary: false },
      {
        onSuccess: (resume) => {
          toast({ message: "Резюме создано" });
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

  let body: ReactNode;
  if (query.isPending) {
    body = <ResumesSkeleton />;
  } else if (query.isError) {
    body = <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  } else if (query.data.items.length === 0) {
    body = (
      <EmptyState
        icon={FileText}
        title="Создайте первое резюме"
        description="Несколько версий для разных ролей помогут точнее видеть соответствие вакансиям."
        action={
          <Button variant="primary" onClick={createBlank} disabled={create.isPending}>
            <Plus size={16} aria-hidden /> Новое резюме
          </Button>
        }
      />
    );
  } else {
    const items = query.data.items;
    body = (
      <>
        <p className="mb-4 text-[13px] text-ink-muted">
          {items.length}{" "}
          {pluralRu(items.length, ["резюме", "резюме", "резюме"])}
        </p>
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((resume, index) => (
            <motion.li key={resume.id} {...rise(index, reduced)}>
              <ResumeCard
                resume={resume}
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
          <li>
            <button
              type="button"
              onClick={createBlank}
              disabled={create.isPending}
              className="flex min-h-[270px] w-full flex-col items-center justify-center rounded-card border border-dashed border-line-strong bg-transparent text-center hover:border-accent-border hover:bg-surface disabled:opacity-60"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-surface text-accent-muted shadow-card">
                <Plus size={18} aria-hidden />
              </span>
              <span className="mt-3 text-[14px] font-medium text-ink-body">Добавить ещё одно</span>
              <span className="mt-1 text-[13px] text-ink-muted">Для новой цели или языка</span>
            </button>
          </li>
        </ul>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Ваши материалы"
        title="Мои резюме"
        description="Несколько точных версий для разных ролей. Обновляйте их по мере того, как растёт ваш опыт."
        actions={
          <Button variant="primary" onClick={createBlank} disabled={create.isPending}>
            <Plus size={16} aria-hidden /> Новое резюме
          </Button>
        }
      />
      {body}
      <ConfirmDialog
        open={deleteTarget !== null}
        title="Удалить резюме?"
        description={
          deleteTarget?.is_primary
            ? "Это основное резюме — основным станет самое свежее из оставшихся."
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

function ResumesSkeleton() {
  return (
    <ul aria-busy="true" aria-label="Загрузка резюме" className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 3 }, (_, index) => (
        <li key={index} className="rounded-card border border-line bg-surface p-5 shadow-card">
          <div className="flex justify-between">
            <Skeleton className="h-10 w-10 rounded-lg" />
            <Skeleton className="h-8 w-8 rounded-lg" />
          </div>
          <Skeleton className="mt-5 h-5 w-3/5" />
          <Skeleton className="mt-2 h-4 w-2/5" />
          <Skeleton className="mt-5 h-4 w-4/5" />
          <Skeleton className="mt-4 h-8 w-full" />
        </li>
      ))}
    </ul>
  );
}
