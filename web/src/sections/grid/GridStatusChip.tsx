"use client";

import { Button } from "@opal/components";
import { SvgActivity } from "@opal/icons";

import SimplePopover from "@/refresh-components/SimplePopover";
import Text from "@/refresh-components/texts/Text";
import useGridWorkers from "@/hooks/useGridWorkers";
import useGridModelStatus from "@/hooks/useGridModelStatus";
import { cn } from "@opal/utils";

/**
 * AIPG fork: a compact header chip showing how many AI Power Grid workers are
 * online. Clicking it opens a dropdown listing each served model with its live
 * worker count + recent tokens/sec, then the individual online workers.
 *
 * Pure read-only: data comes from the backend grid-status proxy
 * (`/api/grid/workers`, `/api/grid/models`). Renders nothing if the grid is
 * unreachable/unconfigured so it never breaks the chat header.
 */
export default function GridStatusChip() {
  const { count, workers, error: workersError } = useGridWorkers();
  const { models } = useGridModelStatus();

  // Grid not configured / unreachable — stay invisible rather than show an error.
  if (workersError) return null;

  // Online first, then busiest (most workers), then name — so "what's fast and
  // available right now" is at the top.
  const sortedModels = [...models].sort(
    (a, b) =>
      Number(b.count > 0) - Number(a.count > 0) ||
      b.count - a.count ||
      a.name.localeCompare(b.name)
  );
  const modelsServed = models.filter((m) => m.count > 0).length;

  return (
    <SimplePopover
      side="bottom"
      align="end"
      trigger={
        <Button
          icon={SvgActivity}
          prominence="tertiary"
          aria-label="grid-status"
        >
          {String(count)}
        </Button>
      }
    >
      <div className="p-3 w-80 max-h-[28rem] overflow-y-auto flex flex-col gap-3">
        <div className="flex flex-col gap-0.5">
          <Text text02 mainUiAction>
            AI Power Grid
          </Text>
          <Text text03 secondaryBody>
            {count} {count === 1 ? "worker" : "workers"} online
            {modelsServed > 0 ? ` · ${modelsServed} models live` : ""}
          </Text>
        </div>

        {models.length > 0 && (
          <div className="flex flex-col gap-1">
            <Text text04 secondaryAction>
              Models
            </Text>
            {sortedModels.map((m) => {
              const stats = [
                `${m.count}×`,
                m.tokens_per_s != null ? `${m.tokens_per_s} t/s` : null,
                m.avg_ttft_s != null ? `${m.avg_ttft_s}s TTFT` : null,
              ]
                .filter(Boolean)
                .join(" · ");
              return (
                <div
                  key={`${m.name}-${m.type}`}
                  className={cn(
                    "flex flex-row items-center justify-between gap-2 py-0.5",
                    m.count === 0 && "opacity-50"
                  )}
                >
                  <div className="flex flex-row items-center gap-2 min-w-0">
                    <span
                      className={cn(
                        "w-1.5 h-1.5 rounded-full shrink-0",
                        m.count > 0
                          ? "bg-status-success-05"
                          : "bg-background-neutral-04"
                      )}
                    />
                    <Text text02 secondaryBody nowrap className="truncate">
                      {m.name}
                    </Text>
                  </div>
                  <Text text04 secondaryBody nowrap>
                    {stats}
                  </Text>
                </div>
              );
            })}
          </div>
        )}

        {workers.length > 0 && (
          <div className="flex flex-col gap-1">
            <Text text04 secondaryAction>
              Workers
            </Text>
            {workers.map((w) => (
              <div
                key={w.id}
                className="flex flex-row items-center justify-between gap-2 py-0.5"
              >
                <Text text02 secondaryBody nowrap className="truncate">
                  {w.name}
                </Text>
                <Text text04 secondaryBody nowrap className="truncate max-w-[10rem]">
                  {w.models.join(", ")}
                </Text>
              </div>
            ))}
          </div>
        )}

        {count === 0 && models.length === 0 && (
          <Text text04 secondaryBody>
            No workers online right now.
          </Text>
        )}
      </div>
    </SimplePopover>
  );
}
