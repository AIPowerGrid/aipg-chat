import useSWR from "swr";

import { errorHandlingFetcher } from "@/lib/fetcher";
import { SWR_KEYS } from "@/lib/swr-keys";
import { GridModelStatus } from "@/lib/grid/interfaces";

/**
 * AIPG fork: per-model live status + recent performance (t/s, TTFT, latency,
 * worker count) from the grid. Used by the header workers dropdown and the
 * per-message info popover.
 */
export default function useGridModelStatus(enabled: boolean = true) {
  const { data, error, isLoading, mutate } = useSWR<GridModelStatus[]>(
    enabled ? SWR_KEYS.gridModelStatus : null,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      refreshInterval: 30_000,
      dedupingInterval: 15_000,
    }
  );

  return {
    models: data ?? [],
    isLoading,
    error,
    refetch: mutate,
  };
}
