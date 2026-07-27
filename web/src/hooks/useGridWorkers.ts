import useSWR from "swr";

import { errorHandlingFetcher } from "@/lib/fetcher";
import { SWR_KEYS } from "@/lib/swr-keys";
import { GridWorkersResponse } from "@/lib/grid/interfaces";

/**
 * AIPG fork: live list of grid workers currently connected. Polls every 30s so
 * the header chip reflects capacity without hammering the grid.
 */
export default function useGridWorkers(enabled: boolean = true) {
  const { data, error, isLoading, mutate } = useSWR<GridWorkersResponse>(
    enabled ? SWR_KEYS.gridWorkers : null,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      refreshInterval: 30_000,
      dedupingInterval: 15_000,
    }
  );

  return {
    workers: data?.workers ?? [],
    count: data?.count ?? 0,
    isLoading,
    error,
    refetch: mutate,
  };
}
