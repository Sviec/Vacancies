import { isRouteErrorResponse, useNavigate, useRouteError } from "react-router";

import { ErrorState } from "@/components/ui/ErrorState";

/** Ошибка рендера или маршрута: показывается внутри оболочки, шапка остаётся. */
export function RouteError() {
  const error = useRouteError();
  const navigate = useNavigate();
  const shown = isRouteErrorResponse(error)
    ? new Error(`${error.status} ${error.statusText}`)
    : error;
  return (
    <ErrorState
      title="Что-то пошло не так"
      error={shown}
      onRetry={() => navigate(0)}
    />
  );
}
