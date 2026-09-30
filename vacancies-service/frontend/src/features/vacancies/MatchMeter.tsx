import { cn } from "@/lib/cn";
import { formatPercent } from "@/lib/format";
import { matchTone } from "@/lib/match-reasons";
import type { MatchTone } from "@/lib/match-reasons";

const TONE_CLASSES: Record<MatchTone, string> = {
  positive: "text-positive",
  accent: "text-accent",
  muted: "text-ink-muted",
};

const SIZES = {
  sm: { box: 44, radius: 18, stroke: 3, text: "text-[13px]" },
  lg: { box: 58, radius: 24, stroke: 4, text: "text-[13px]" },
} as const;

interface MatchMeterProps {
  score: number;
  size?: keyof typeof SIZES;
  className?: string;
}

/**
 * Кольцо процента соответствия (ScoreRing макета). Цвет — через currentColor
 * токена тона; `-rotate-90` статичный: дуга начинается сверху.
 */
export function MatchMeter({ score, size = "sm", className }: MatchMeterProps) {
  const { box, radius, stroke, text } = SIZES[size];
  const circumference = 2 * Math.PI * radius;
  const value = Math.min(Math.max(score, 0), 100);
  const label = `Соответствие ${formatPercent(value)}`;
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={cn("relative inline-flex shrink-0 items-center justify-center", TONE_CLASSES[matchTone(value)], className)}
      style={{ width: box, height: box }}
    >
      <svg className="-rotate-90" width={box} height={box} viewBox={`0 0 ${box} ${box}`} aria-hidden>
        <circle cx={box / 2} cy={box / 2} r={radius} fill="none" className="stroke-line" strokeWidth={stroke} />
        <circle
          cx={box / 2}
          cy={box / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={circumference - (value / 100) * circumference}
        />
      </svg>
      <span aria-hidden className={cn("absolute font-semibold tabular-nums", text)}>
        {Math.round(value)}
      </span>
    </span>
  );
}
