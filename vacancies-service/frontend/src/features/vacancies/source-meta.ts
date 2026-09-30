import { Globe, Rss, Send } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useMemo } from "react";

import { useSources } from "@/api/sources";
import type { SourceType } from "@/api/types";

export type SourceTypes = Readonly<Record<string, SourceType>>;

/** Тип каждого источника по slug — для иконок бейджей; пока грузится — пусто. */
export function useSourceTypes(): SourceTypes {
  const { data } = useSources();
  return useMemo(
    () => Object.fromEntries((data?.items ?? []).map((item) => [item.slug, item.source_type])),
    [data],
  );
}

export function sourceIcon(type: SourceType | undefined): LucideIcon {
  if (type === "telegram") {
    return Send;
  }
  if (type === "html") {
    return Globe;
  }
  return Rss;
}
