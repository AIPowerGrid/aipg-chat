"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import {
  Button,
  InputTypeIn,
  LineItemButton,
  PopoverMenu,
  Text,
  Tooltip,
} from "@opal/components";
import { SvgCheck, SvgChevronRight, SvgInfoSmall } from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import { LLMOption } from "./interfaces";
import { buildLlmOptions, groupLlmOptions } from "./LLMPopover";
import { LLMProviderDescriptor } from "@/lib/languageModels/types";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/refresh-components/Collapsible";
import { cn } from "@opal/utils";
import { Interactive } from "@opal/core";
import { ContentAction } from "@opal/layouts";
import useGridModelStatus from "@/hooks/useGridModelStatus";
import useGridWorkers from "@/hooks/useGridWorkers";
import { GridModelStatus, GridWorker } from "@/lib/grid/interfaces";

// Compact context-window label, e.g. 131072 -> "128K", 262144 -> "256K".
function formatContext(tokens: number): string {
  return tokens >= 1024 ? `${Math.round(tokens / 1024)}K` : String(tokens);
}

function formatSeconds(seconds: number): string {
  return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds}s`;
}

interface ModelInfoTooltipProps {
  option: LLMOption;
  grid?: GridModelStatus;
  workers: GridWorker[];
  isLoading: boolean;
}

function ModelInfoTooltip({
  option,
  grid,
  workers,
  isLoading,
}: ModelInfoTooltipProps) {
  const capabilities = [
    option.supportsReasoning ? "Reasoning" : null,
    option.supportsImageInput ? "Vision" : null,
  ].filter(Boolean) as string[];

  const tooltip = (
    <div className="flex w-56 flex-col gap-2 p-1">
      <div className="flex flex-col gap-0.5">
        <Text font="main-ui-action" color="inherit">
          {option.displayName}
        </Text>
        <div className="opacity-70">
          <Text font="secondary-body" color="inherit">
            {capabilities.length > 0
              ? capabilities.join(" · ")
              : "Text generation"}
          </Text>
        </div>
      </div>

      {grid ? (
        <div className="flex flex-col gap-1.5 border-t border-border-01 pt-2">
          <ModelStat
            label="Availability"
            value={`${grid.count} online ${grid.count === 1 ? "worker" : "workers"}`}
            active={grid.count > 0}
          />
          <ModelStat
            label="Context"
            value={
              grid.max_context_length
                ? `${formatContext(grid.max_context_length)} tokens`
                : "Not reported"
            }
          />
          <ModelStat
            label="Throughput"
            value={
              grid.tokens_per_s != null
                ? `${grid.tokens_per_s} tokens/sec`
                : "Not reported"
            }
          />
          <ModelStat
            label="First token"
            value={
              grid.avg_ttft_s != null
                ? formatSeconds(grid.avg_ttft_s)
                : "Not reported"
            }
          />
          <ModelStat
            label="Avg latency"
            value={
              grid.avg_latency_s != null
                ? formatSeconds(grid.avg_latency_s)
                : "Not reported"
            }
          />
          <ModelStat label="24h samples" value={String(grid.samples)} />

          <div className="flex flex-col gap-1 border-t border-border-01 pt-2">
            <div className="opacity-70">
              <Text font="secondary-action" color="inherit">
                Serving workers
              </Text>
            </div>
            {workers.length > 0 ? (
              <>
                {workers.slice(0, 3).map((worker) => (
                  <div key={worker.id} className="flex items-center gap-1.5">
                    <span className="size-1.5 shrink-0 rounded-full bg-status-success-05" />
                    <div className="min-w-0 truncate">
                      <Text font="secondary-body" color="inherit" nowrap>
                        {worker.name}
                      </Text>
                    </div>
                  </div>
                ))}
                {workers.length > 3 && (
                  <div className="opacity-70">
                    <Text font="secondary-body" color="inherit">
                      {`+${workers.length - 3} more`}
                    </Text>
                  </div>
                )}
              </>
            ) : (
              <div className="opacity-70">
                <Text font="secondary-body" color="inherit">
                  No online workers reported.
                </Text>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="opacity-70">
          <Text font="secondary-body" color="inherit">
            {isLoading
              ? "Loading live Grid stats..."
              : "Live Grid stats are not available for this model."}
          </Text>
        </div>
      )}
    </div>
  );

  return (
    <Tooltip tooltip={tooltip} side="right" align="start" delayDuration={150}>
      <span
        aria-label={`Information about ${option.displayName}`}
        className={cn(
          "inline-flex size-6 items-center justify-center rounded",
          "text-text-04 hover:bg-background-neutral-03 hover:text-text-02"
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <SvgInfoSmall size={14} />
      </span>
    </Tooltip>
  );
}

interface ModelStatProps {
  label: string;
  value: string;
  active?: boolean;
}

function ModelStat({ label, value, active }: ModelStatProps) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="opacity-70">
        <Text font="secondary-body" color="inherit">
          {label}
        </Text>
      </div>
      <div className="flex min-w-0 items-center gap-1.5">
        {active !== undefined && (
          <span
            className={cn(
              "size-1.5 shrink-0 rounded-full",
              active ? "bg-status-success-05" : "bg-text-04"
            )}
          />
        )}
        <Text font="secondary-body" color="inherit" nowrap>
          {value}
        </Text>
      </div>
    </div>
  );
}

export interface ModelListContentProps {
  llmProviders: LLMProviderDescriptor[] | undefined;
  currentModelName?: string;
  requiresImageInput?: boolean;
  onSelect: (option: LLMOption) => void;
  isSelected: (option: LLMOption) => boolean;
  isDisabled?: (option: LLMOption) => boolean;
  scrollContainerRef?: React.RefObject<HTMLDivElement | null>;
  isLoading?: boolean;
  footer?: React.ReactNode;
}

export default function ModelListContent({
  llmProviders,
  currentModelName,
  requiresImageInput,
  onSelect,
  isSelected,
  isDisabled,
  scrollContainerRef: externalScrollRef,
  isLoading,
  footer,
}: ModelListContentProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const internalScrollRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = externalScrollRef ?? internalScrollRef;

  // Live AI Power Grid per-model status (worker count + recent t/s). Used to
  // annotate each model row with how many workers serve it + a hover summary.
  const { models: gridModels, isLoading: gridIsLoading } = useGridModelStatus();
  const { workers: gridWorkers, isLoading: workersAreLoading } =
    useGridWorkers();
  const gridByModel = useMemo(() => {
    const map = new Map<string, GridModelStatus>();
    for (const m of gridModels) map.set(m.name.toLowerCase(), m);
    return map;
  }, [gridModels]);

  const gridStatusFor = (modelName: string): GridModelStatus | undefined => {
    const lower = modelName.toLowerCase();
    return (
      gridByModel.get(lower) ||
      gridModels.find((m) => lower.endsWith(m.name.toLowerCase()))
    );
  };

  const workersFor = (modelName: string): GridWorker[] => {
    const lower = modelName.toLowerCase();
    return gridWorkers.filter((worker) =>
      worker.models.some((advertisedModel) => {
        const advertised = advertisedModel.toLowerCase();
        return (
          lower === advertised ||
          lower.endsWith(advertised) ||
          advertised.endsWith(lower)
        );
      })
    );
  };

  const llmOptions = useMemo(
    () => buildLlmOptions(llmProviders, currentModelName),
    [llmProviders, currentModelName]
  );

  const filteredOptions = useMemo(() => {
    let result = llmOptions;
    if (requiresImageInput) {
      result = result.filter((opt) => opt.supportsImageInput);
    }
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (opt) =>
          opt.displayName.toLowerCase().includes(query) ||
          opt.modelName.toLowerCase().includes(query) ||
          (opt.vendor && opt.vendor.toLowerCase().includes(query))
      );
    }
    return result;
  }, [llmOptions, searchQuery, requiresImageInput]);

  const groupedOptions = useMemo(
    () => groupLlmOptions(filteredOptions),
    [filteredOptions]
  );

  // Find which group contains a currently-selected model (for auto-expand)
  const defaultGroupKey = useMemo(() => {
    for (const group of groupedOptions) {
      if (group.options.some((opt) => isSelected(opt))) {
        return group.key;
      }
    }
    return groupedOptions[0]?.key ?? "";
  }, [groupedOptions, isSelected]);

  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    new Set([defaultGroupKey])
  );

  // Reset expanded groups when default changes (e.g. popover re-opens)
  useEffect(() => {
    setExpandedGroups(new Set([defaultGroupKey]));
  }, [defaultGroupKey]);

  const isSearching = searchQuery.trim().length > 0;

  const toggleGroup = (key: string) => {
    if (isSearching) return;
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const isGroupOpen = (key: string) => isSearching || expandedGroups.has(key);

  const renderModelItem = (option: LLMOption) => {
    const selected = isSelected(option);
    const disabled = isDisabled?.(option) ?? false;

    const grid = gridStatusFor(option.modelName);

    return (
      <LineItemButton
        key={`${option.provider}:${option.modelName}`}
        selectVariant="select-heavy"
        state={selected ? "selected" : "empty"}
        title={option.displayName}
        onClick={() => onSelect(option)}
        rightChildren={
          <div className="flex h-6 items-center gap-1">
            <ModelInfoTooltip
              option={option}
              grid={grid}
              workers={workersFor(option.modelName)}
              isLoading={gridIsLoading || workersAreLoading}
            />
            {/* Always reserve the checkmark's slot so the badge column lines up
                across selected and non-selected rows. */}
            <div className="w-4 flex items-center justify-center shrink-0">
              {selected && (
                <SvgCheck className="text-action-link-05" size={16} />
              )}
            </div>
          </div>
        }
        sizePreset="main-ui"
        rounding="sm"
      />
    );
  };

  return (
    <Section gap={0.5}>
      <InputTypeIn
        searchIcon
        variant="internal"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder="Search models..."
      />

      <PopoverMenu
        scrollContainerRef={scrollContainerRef}
        menuClassName="max-h-[min(70vh,34rem)]"
      >
        {isLoading
          ? [
              <Text key="loading" font="secondary-body" color="text-03">
                Loading models...
              </Text>,
            ]
          : groupedOptions.length === 0
            ? [
                <Text key="empty" font="secondary-body" color="text-03">
                  No models found
                </Text>,
              ]
            : groupedOptions.length === 1
              ? [
                  <Section key="single-provider" gap={1}>
                    {groupedOptions[0]!.options.map(renderModelItem)}
                  </Section>,
                ]
              : groupedOptions.map((group) => {
                  const open = isGroupOpen(group.key);
                  return (
                    <Collapsible
                      key={group.key}
                      open={open}
                      onOpenChange={() => toggleGroup(group.key)}
                      className="flex flex-col gap-1"
                    >
                      <CollapsibleTrigger asChild>
                        <Interactive.Stateless prominence="tertiary">
                          <Interactive.Container
                            size="fit"
                            rounding="sm"
                            width="full"
                          >
                            <div className="pl-2 pr-1 py-1 w-full">
                              <ContentAction
                                sizePreset="secondary"
                                variant="body"
                                color="muted"
                                icon={group.Icon}
                                title={group.displayName}
                                padding="fit"
                                rightChildren={
                                  <Section>
                                    <Button
                                      icon={(props) => (
                                        <SvgChevronRight
                                          {...props}
                                          className={cn(
                                            "transition-all",
                                            open && "rotate-90",
                                            props.className
                                          )}
                                        />
                                      )}
                                      prominence="tertiary"
                                      size="sm"
                                    />
                                  </Section>
                                }
                                center
                              />
                            </div>
                          </Interactive.Container>
                        </Interactive.Stateless>
                      </CollapsibleTrigger>

                      <CollapsibleContent>
                        <Section gap={0.25}>
                          {group.options.map(renderModelItem)}
                        </Section>
                      </CollapsibleContent>
                    </Collapsible>
                  );
                })}
      </PopoverMenu>

      {footer}
    </Section>
  );
}
