import { Compass } from "lucide-react";
import { Link } from "react-router";

import { PageHeader } from "@/components/layout/AppShell";
import { buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";

export function NotFound() {
  return (
    <>
      <PageHeader title="Страница не найдена" />
      <EmptyState
        icon={Compass}
        title="Такой страницы нет"
        description="Возможно, ссылка устарела. Вернитесь к ленте вакансий."
        action={
          <Link to="/vacancies" className={buttonClasses("primary")}>
            К вакансиям
          </Link>
        }
      />
    </>
  );
}
