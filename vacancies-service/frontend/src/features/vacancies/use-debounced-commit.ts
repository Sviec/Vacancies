import { useEffect, useRef, useState } from "react";

/**
 * Текстовое поле, которое пишет значение в URL через `delayMs` после
 * последнего ввода. Внешнее изменение (сброс фильтров, «назад») подменяет
 * текст, но только если оно не совпадает с уже введённым после нормализации —
 * иначе «съедался бы» набираемый пробел.
 */
export function useDebouncedCommit(
  value: string,
  commit: (text: string) => void,
  normalize: (text: string) => string,
  delayMs: number,
): [string, (text: string) => void] {
  const [text, setText] = useState(value);
  const [prevValue, setPrevValue] = useState(value);
  if (value !== prevValue) {
    setPrevValue(value);
    if (normalize(text) !== value) {
      setText(value);
    }
  }

  const commitRef = useRef(commit);
  const normalizeRef = useRef(normalize);
  useEffect(() => {
    commitRef.current = commit;
    normalizeRef.current = normalize;
  });

  useEffect(() => {
    if (normalizeRef.current(text) === value) {
      return;
    }
    const timer = window.setTimeout(() => commitRef.current(text), delayMs);
    return () => window.clearTimeout(timer);
  }, [text, value, delayMs]);

  return [text, setText];
}
