import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import type { ResumeScoreDetails, ScoreCriterionKey } from "@/api/types";
import { formatScore10 } from "@/lib/format";
import { useReducedMotionSafe } from "@/lib/motion";

const SHORT_LABELS: Record<ScoreCriterionKey, string> = {
  completeness: "Полнота",
  experience_quality: "Опыт",
  measurable_achievements: "Метрики",
  skills_relevance: "Навыки",
  chronology: "Хронология",
  education_courses: "Образование",
  languages: "Языки",
  goals_specificity: "Цели",
};

interface ScoreRadarProps {
  details: ResumeScoreDetails;
}

/**
 * Радар по 8 критериям. Ось — points/weight×100, иначе веса 0,5 и 2,0
 * несравнимы. Цвет через currentColor обёртки text-accent.
 */
export function ScoreRadar({ details }: ScoreRadarProps) {
  const reduced = useReducedMotionSafe();
  // TODO: радар нормирует критерии в проценты от веса — иначе оси 0,5 и 2,0 несопоставимы.
  const data = details.criteria.map((item) => {
    const ratio = item.weight > 0 ? (item.points / item.weight) * 100 : 0;
    return {
      key: item.key,
      label: SHORT_LABELS[item.key] ?? item.name,
      value: Math.min(Math.max(ratio, 0), 100),
      points: item.points,
      weight: item.weight,
    };
  });

  return (
    <div className="h-[260px] w-full text-accent">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="68%">
          <PolarGrid className="stroke-line" />
          <PolarAngleAxis
            dataKey="label"
            tick={{ fill: "currentColor", fontSize: 13, opacity: 0.7 }}
          />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Radar
            dataKey="value"
            stroke="currentColor"
            fill="currentColor"
            fillOpacity={0.15}
            strokeWidth={1.5}
            isAnimationActive={!reduced}
            animationDuration={220}
            animationEasing="ease-out"
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.[0]) {
                return null;
              }
              const row = payload[0].payload as (typeof data)[number];
              return (
                <div className="rounded-md border border-line bg-surface px-3 py-2 text-[13px] text-ink shadow-pop">
                  {formatScore10(row.points)} из {formatScore10(row.weight)}
                </div>
              );
            }}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
