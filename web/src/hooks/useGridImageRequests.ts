import useSWR from "swr";
import { readImageRequests } from "@/lib/grid/imageRecovery";

export default function useGridImageRequests(
  messageId: number | undefined,
  userId: string | undefined,
  enabled: boolean,
  isGenerating: boolean
) {
  return useSWR(
    enabled && userId && messageId && messageId > 0
      ? [`/api/grid/images?message_id=${messageId}`, userId, isGenerating]
      : null,
    ([url]: [string, string, boolean]) => readImageRequests(url),
    {
      refreshInterval: isGenerating ? 15_000 : 0,
      revalidateOnFocus: true,
      shouldRetryOnError: false,
      keepPreviousData: false,
    }
  );
}
