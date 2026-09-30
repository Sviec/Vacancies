import { Construction } from "lucide-react";

import { PageHeader } from "@/components/layout/AppShell";
import { EmptyState } from "@/components/ui/EmptyState";

interface StubPageProps {
  eyebrow: string;
  title: string;
  description: string;
  substage: "8b" | "8c" | "8d";
}

/** Временная страница: каркас оболочки уже работает, экран — на следующем подэтапе. */
export function StubPage({ eyebrow, title, description, substage }: StubPageProps) {
  return (
    <>
      <PageHeader eyebrow={eyebrow} title={title} description={description} />
      <EmptyState
        icon={Construction}
        title={`Экран появится на подэтапе ${substage}`}
        description="Навигация, тема и индикатор API уже работают — сам экран подключается следующим шагом этапа 8."
      />
    </>
  );
}
