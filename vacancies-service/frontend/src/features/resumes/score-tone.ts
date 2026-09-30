/** Тон оценки резюме 0–10 (scoreTone макета через токены). */

export type ScoreTone = "positive" | "warn" | "danger";

// TODO: пороги цвета оценки резюме — 8 и 6,5 (по scoreTone макета).
export function scoreTone(score: number | null | undefined): ScoreTone {
  if (score == null) {
    return "danger";
  }
  if (score >= 8) {
    return "positive";
  }
  if (score >= 6.5) {
    return "warn";
  }
  return "danger";
}

export function scoreToneLabel(tone: ScoreTone): string {
  if (tone === "positive") {
    return "сильное";
  }
  if (tone === "warn") {
    return "можно усилить";
  }
  return "нужно внимание";
}

export const SCORE_TONE_TEXT: Record<ScoreTone, string> = {
  positive: "text-positive",
  warn: "text-warn",
  danger: "text-danger",
};

export const SCORE_TONE_SOFT: Record<ScoreTone, string> = {
  positive: "bg-positive-soft text-positive",
  warn: "bg-warn-soft text-warn",
  danger: "bg-danger-soft text-danger",
};
