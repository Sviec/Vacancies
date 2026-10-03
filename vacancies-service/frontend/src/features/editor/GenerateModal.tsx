import { Sparkles } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import { useGenerateResume } from "@/api/resumes";
import { Button } from "@/components/ui/Button";
import { describeError } from "@/components/ui/ErrorState";
import { TextArea, TextField } from "@/components/ui/fields";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toaster";
import { FEATURES } from "@/lib/features";

interface GenerateModalProps {
  open: boolean;
  onClose: () => void;
}

/** Модалка ИИ-генерации: черновик сохраняется и открывается в редакторе. */
export function GenerateModal({ open, onClose }: GenerateModalProps) {
  const navigate = useNavigate();
  const toast = useToast();
  const generate = useGenerateResume();
  const [brief, setBrief] = useState("");
  const [target, setTarget] = useState("");
  // TODO: лимит raw_text 10 000 символов только на фронте, API его не проверяет.
  const tooLong = brief.length > 10_000;
  const canSubmit = FEATURES.aiGenerate && brief.trim() !== "" && !tooLong;

  function submit() {
    if (!canSubmit || generate.isPending) {
      return;
    }
    const position = target.trim();
    generate.mutate(
      {
        raw_text: brief.trim(),
        target_position: position === "" ? null : position,
      },
      {
        onSuccess: (resume) => {
          onClose();
          navigate(`/resumes/${resume.id}`);
        },
        onError: (error) => {
          toast({ message: describeError(error), tone: "danger" });
        },
      },
    );
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Сгенерировать через ИИ"
      description="Опишите опыт обычными словами — черновик откроется в редакторе."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Закрыть
          </Button>
          <Button
            variant="primary"
            disabled={!canSubmit || generate.isPending}
            title={FEATURES.aiGenerate ? undefined : "ИИ-генерация подключается на этапе 10"}
            onClick={submit}
          >
            {generate.isPending ? (
              "Генерируем…"
            ) : (
              <>
                <Sparkles size={15} aria-hidden /> Сгенерировать
              </>
            )}
          </Button>
        </>
      }
    >
      {!FEATURES.aiGenerate && (
        <p className="mb-4 rounded-lg bg-accent-soft px-3 py-3 text-[13px] leading-5 text-accent">
          ИИ-генерация подключается на этапе 10 — пока заполните резюме вручную
        </p>
      )}
      <div className="space-y-4">
        <TextArea
          label="Расскажите о себе и опыте"
          value={brief}
          error={tooLong ? "Не длиннее 10 000 символов" : undefined}
          rows={5}
          maxLength={10_000}
          onChange={(event) => setBrief(event.target.value)}
          placeholder="Например: 3 года в продуктовой разработке, хочу перейти в финтех"
        />
        <TextField
          label="Целевая позиция"
          hint="Необязательно"
          value={target}
          onChange={(event) => setTarget(event.target.value)}
          placeholder="Python-разработчик"
        />
      </div>
    </Modal>
  );
}
