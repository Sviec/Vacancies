import { useEffect, useRef } from "react";

import { useScoreResume } from "@/api/resumes";
import { parseScoreDetails } from "@/api/types";
import type { ResumeRead, ScoreCriterionKey } from "@/api/types";
import { ScoreCircle } from "@/features/editor/ScoreCircle";
import { ScoreRadar } from "@/features/editor/ScoreRadar";
import { SCORE_TONE_SOFT, scoreTone } from "@/features/resumes/score-tone";
import { cn } from "@/lib/cn";
import { formatScore10 } from "@/lib/format";
import { useReducedMotionSafe } from "@/lib/motion";

const SECTION_BY_CRITERION: Partial<Record<ScoreCriterionKey, string>> = {
  completeness: "basics",
  experience_quality: "experience",
  measurable_achievements: "experience",
  chronology: "experience",
  skills_relevance: "skills",
  education_courses: "education",
  languages: "languages",
  goals_specificity: "goals",
};

interface ScorePanelProps {
  resume: ResumeRead;
  dirty: boolean;
  saving: boolean;
}

/** Панель серверной оценки: круг, радар, критерии и рекомендации. */
export function ScorePanel({ resume, dirty, saving }: ScorePanelProps) {
  const details = parseScoreDetails(resume.score_details);
  const scoreMutation = useScoreResume();
  const scoredOnce = useRef<string | null>(null);
  const mutateScore = scoreMutation.mutate;
  const scorePending = scoreMutation.isPending;
  const reducedMotion = useReducedMotionSafe();

  useEffect(() => {
    if (resume.score != null || details) {
      return;
    }
    if (scoredOnce.current === resume.id || scorePending) {
      return;
    }
    scoredOnce.current = resume.id;
    mutateScore(resume.id);
  }, [resume.id, resume.score, details, mutateScore, scorePending]);

  const score = resume.score ?? details?.score ?? null;
  const tone = scoreTone(score);
  const pendingScore = dirty || saving;

  const recommendations =
    details?.criteria.filter((item) => item.recommendation && item.recommendation.trim()) ?? [];

  return (
    <aside className="lg:sticky lg:top-24 lg:self-start">
      <div className="rounded-card border border-line bg-surface p-5 shadow-card">
        <div className="text-[13px] font-semibold tracking-[0.12em] text-accent-muted uppercase">
          Качество резюме
        </div>
        <h2 className="mt-2 text-[15px] font-semibold text-ink">Ваш прогресс</h2>

        <div className="mt-5 flex items-center gap-4">
          <ScoreCircle score={score} />
          <div>
            <span className={cn("inline-flex rounded-md px-2 py-1 text-[13px] font-medium", SCORE_TONE_SOFT[tone])}>
              {score == null ? "оценка появится после сохранения" : score >= 8 ? "сильная база" : "есть точки роста"}
            </span>
            {pendingScore && (
              <p className="mt-2 max-w-[160px] text-[13px] leading-5 text-ink-muted">
                Оценка обновится после сохранения
              </p>
            )}
          </div>
        </div>

        {details ? (
          <>
            <div className="mt-5 border-t border-line pt-5">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-[13px] font-semibold text-ink-body">Профиль качества</h3>
                <span className="text-[13px] text-ink-muted">8 критериев</span>
              </div>
              <ScoreRadar details={details} />
            </div>

            <ul className="mt-4 space-y-3 border-t border-line pt-5">
              {details.criteria.map((item) => {
                const ratio = item.weight > 0 ? Math.min(item.points / item.weight, 1) : 0;
                return (
                  <li key={item.key}>
                    <div className="mb-1 flex items-baseline justify-between gap-3">
                      <span className="text-[13px] font-medium text-ink">{item.name}</span>
                      <span className="text-[13px] text-ink-muted tabular-nums">
                        {formatScore10(item.points)} / {formatScore10(item.weight)}
                      </span>
                    </div>
                    <div className="h-1 overflow-hidden rounded-full bg-surface-inset" aria-hidden>
                      <div
                        className="h-full rounded-full bg-accent"
                        style={{ width: `${ratio * 100}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>

            <div className="mt-5 border-t border-line pt-5">
              <h3 className="text-[13px] font-semibold text-ink-body">Рекомендации</h3>
              {recommendations.length === 0 ? (
                <p className="mt-3 text-[13px] leading-5 text-ink-muted">Резюме заполнено хорошо</p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {recommendations.map((item) => {
                    const sectionId = SECTION_BY_CRITERION[item.key];
                    return (
                      <li key={item.key}>
                        <button
                          type="button"
                          className="w-full text-left"
                          onClick={() => {
                            if (sectionId) {
                              document.getElementById(sectionId)?.scrollIntoView({
                                behavior: reducedMotion ? "auto" : "smooth",
                                block: "start",
                              });
                            }
                          }}
                        >
                          <p className="text-[13px] font-medium text-ink">{item.name}</p>
                          <p className="mt-1 text-[13px] leading-5 text-ink-muted">
                            {item.recommendation}
                          </p>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </>
        ) : (
          <p className="mt-5 text-[13px] text-ink-muted">
            {scoreMutation.isPending
              ? "Считаем оценку…"
              : "Детали оценки появятся после сохранения резюме."}
          </p>
        )}
      </div>
    </aside>
  );
}
