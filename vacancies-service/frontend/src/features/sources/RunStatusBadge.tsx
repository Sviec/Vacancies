import type { RunStatus } from "@/api/types";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { RUN_STATUS_LABELS } from "@/lib/labels";

const TONE: Record<RunStatus, BadgeTone> = {
  success: "positive",
  failed: "danger",
  running: "accent",
};

interface RunStatusBadgeProps {
  status: RunStatus | null;
}

/** Статус последнего запуска или «никогда». */
export function RunStatusBadge({ status }: RunStatusBadgeProps) {
  if (status === null) {
    return <Badge tone="muted">Никогда</Badge>;
  }
  return <Badge tone={TONE[status]}>{RUN_STATUS_LABELS[status]}</Badge>;
}
