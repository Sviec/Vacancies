/**
 * Безопасные обёртки над localStorage: в части приватных режимов хранилище
 * недоступно, и любое обращение бросает исключение.
 */

export function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* значение не переживёт перезагрузку — приемлемая деградация */
  }
}

export function removeStorage(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    /* нечего удалять */
  }
}

/** JSON из хранилища; битое значение — `null`. */
export function readStorageJson<T>(key: string): T | null {
  const raw = readStorage(key);
  if (raw === null) {
    return null;
  }
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function writeStorageJson(key: string, value: unknown): void {
  writeStorage(key, JSON.stringify(value));
}
