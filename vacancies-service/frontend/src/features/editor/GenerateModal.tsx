import { Sparkles } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { TextArea, TextField } from "@/components/ui/fields";
import { Modal } from "@/components/ui/Modal";
import { FEATURES } from "@/lib/features";

interface GenerateModalProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Модалка ИИ-генерации. Отправка выключена флагом FEATURES.aiGenerate
 * до этапа 10; хук useGenerateResume заготовлен, но не вызывается.
 */
export function GenerateModal({ open, onClose }: GenerateModalProps) {
  const [brief, setBrief] = useState("");
  const [target, setTarget] = useState("");
  const tooLong = brief.length > 10_000;
  const canSubmit = FEATURES.aiGenerate && brief.trim() !== "" && !tooLong;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Сгенерировать через ИИ"
      description="Опишите опыт обычными словами — на этапе 10 появится черновик структуры."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Закрыть
          </Button>
          <Button
            variant="primary"
            disabled={!canSubmit}
            title={
              FEATURES.aiGenerate
                ? undefined
                : "ИИ-генерация подключается на этапе 10"
            }
            onClick={() => {
              // TODO: ИИ-генерация включается на этапе 10 — useGenerateResume пока не вызываем.
            }}
          >
            <Sparkles size={15} aria-hidden /> Сгенерировать
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

/** Заготовка хука генерации — не вызывается, пока FEATURES.aiGenerate = false. */
export function useGenerateResume() {
  return {
    mutate: () => {
      throw new Error("ИИ-генерация ещё не подключена");
    },
    isPending: false,
  };
}
