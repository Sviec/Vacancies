import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";

import { parseFeedParams, serializeFeedParams } from "@/features/vacancies/feed-state";
import type { FeedState } from "@/features/vacancies/feed-state";

export type UpdateFeed = (change: (state: FeedState) => FeedState, options?: { replace?: boolean }) => void;

/**
 * Состояние ленты живёт в URL. Обновление функциональное: изменение
 * применяется к актуальным параметрам, а не к снимку из замыкания.
 */
export function useFeedParams(): [FeedState, UpdateFeed] {
  const [searchParams, setSearchParams] = useSearchParams();
  const state = useMemo(() => parseFeedParams(searchParams), [searchParams]);

  const update = useCallback<UpdateFeed>(
    (change, options) => {
      setSearchParams((prev) => serializeFeedParams(change(parseFeedParams(prev))), {
        replace: options?.replace,
        // Смена фильтра или открытие drawer не должны прокручивать ленту наверх.
        preventScrollReset: true,
      });
    },
    [setSearchParams],
  );

  return [state, update];
}
