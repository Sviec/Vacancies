import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate } from "react-router";

import { useCurrentUser, useLogin, useRegister } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/fields";
import { ThemeToggle } from "@/components/ThemeToggle";

interface AuthPageProps {
  mode: "login" | "register";
}

export function AuthPage({ mode }: AuthPageProps) {
  const current = useCurrentUser();
  const login = useLogin();
  const register = useRegister();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const pending = login.isPending || register.isPending;
  const error = login.error ?? register.error;

  if (current.data) {
    return <Navigate to="/vacancies" replace />;
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const body = { email, password };
    if (mode === "login") {
      login.mutate(body);
      return;
    }
    register.mutate(body);
  }

  const message =
    error instanceof ApiError
      ? error.code === "UNAUTHORIZED"
        ? "Неверная почта или пароль"
        : error.code === "CONFLICT"
          ? "Такая почта уже зарегистрирована"
          : error.code === "VALIDATION_ERROR"
            ? "Проверьте почту и пароль: пароль не короче 8 символов"
            : "Не удалось войти"
      : null;

  return (
    <div className="flex min-h-[100dvh] flex-col bg-canvas text-ink">
      <header className="flex h-16 items-center justify-end px-5">
        <ThemeToggle />
      </header>
      <main className="mx-auto flex w-full max-w-[420px] flex-1 flex-col justify-center px-5 pb-16">
        <h1 className="mb-2 text-[24px] font-semibold tracking-[-0.01em]">
          {mode === "login" ? "Вход" : "Регистрация"}
        </h1>
        <p className="mb-8 text-[14px] leading-6 text-ink-muted">
          Резюме и отклики видны только этой учётной записи.
        </p>
        <form className="flex flex-col gap-4 rounded-card border border-line bg-surface p-4" onSubmit={onSubmit}>
          <TextField
            label="Почта"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <TextField
            label="Пароль"
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={8}
          />
          {message && <p className="text-[13px] leading-5 text-danger">{message}</p>}
          <Button type="submit" variant="primary" disabled={pending}>
            {mode === "login" ? "Войти" : "Создать учётную запись"}
          </Button>
        </form>
        <p className="mt-4 text-[13px] text-ink-muted">
          {mode === "login" ? (
            <Link to="/register" className="text-ink underline">
              Нет учётной записи
            </Link>
          ) : (
            <Link to="/login" className="text-ink underline">
              Уже есть учётная запись
            </Link>
          )}
        </p>
      </main>
    </div>
  );
}
