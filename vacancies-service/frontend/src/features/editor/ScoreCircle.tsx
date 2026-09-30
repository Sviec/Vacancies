import { cn } from "@/lib/cn";
import { formatScore10 } from "@/lib/format";
import { SCORE_TONE_TEXT, scoreTone } from "@/features/resumes/score-tone";

interface ScoreCircleProps {
  score: number | null;
}

/** Круг оценки 0–10 (ScoreCircle макета). Цвет через currentColor токена. */
export function ScoreCircle({ score }: ScoreCircleProps) {
  const radius = 44;
  const circumference = 2 * Math.PI * radius;
  const value = score == null ? 0 : Math.min(Math.max(score, 0), 10);
  const tone = scoreTone(score);
  return (
    <div
      className={cn("relative flex h-[118px] w-[118px] items-center justify-center", SCORE_TONE_TEXT[tone])}
      data-testid="score-circle"
    >
      <svg className="-rotate-90" viewBox="0 0 110 110" width="118" height="118" aria-hidden>
        <circle cx="55" cy="55" r={radius} fill="none" className="stroke-line" strokeWidth="6" />
        <circle
          cx="55"
          cy="55"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - (value / 10) * circumference}
          style={{ transition: "stroke-dashoffset 220ms ease-out" }}
        />
      </svg>
      <div className="absolute text-center text-ink">
        <div className="text-[28px] font-semibold tracking-[-0.06em] tabular-nums">
          {score == null ? "—" : formatScore10(score)}
        </div>
        <div className="text-[13px] text-ink-muted">из 10,0</div>
      </div>
    </div>
  );
}
