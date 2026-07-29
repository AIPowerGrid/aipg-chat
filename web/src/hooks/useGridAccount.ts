import useSWR from "swr";

import { errorHandlingFetcher } from "@/lib/fetcher";
import { GridAccountSummary } from "@/lib/grid/interfaces";
import { SWR_KEYS } from "@/lib/swr-keys";

export default function useGridAccount(enabled: boolean = true) {
  return useSWR<GridAccountSummary>(
    enabled ? SWR_KEYS.gridAccount : null,
    errorHandlingFetcher,
    {
      revalidateOnFocus: true,
      refreshInterval: 60_000,
      dedupingInterval: 10_000,
    }
  );
}
