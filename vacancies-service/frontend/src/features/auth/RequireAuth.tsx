import { Navigate, Outlet } from "react-router";

import { useCurrentUser } from "@/api/auth";

export function RequireAuth() {
  const current = useCurrentUser();

  if (current.isPending) {
    return (
      <div className="mx-auto flex min-h-[100dvh] max-w-[420px] flex-col justify-center gap-3 px-5">
        <div className="skeleton h-8 w-40 rounded-lg" />
        <div className="skeleton h-24 rounded-card" />
      </div>
    );
  }

  if (!current.data) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
