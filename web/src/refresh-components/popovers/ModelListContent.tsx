"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { PopoverMenu } from "@opal/components";
import { InputTypeIn } from "@opal/components";
import { Button, LineItemButton, Text } from "@opal/components";
import { SvgCheck, SvgChevronRight } from "@opal/icons";
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
import { SvgActivity } from "@opal/icons";
import useGridModelStatus from "@/hooks/useGridModelStatus";
import { GridModelStatus } from "@/lib/grid/interfaces";

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
  const { models: gridModels } = useGridModelStatus();
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

    const capabilities: string[] = [];
    if (option.supportsReasoning) capabilities.push("Reasoning");
    if (option.supportsImageInput) capabilities.push("Vision");

    // Live grid status for this model: worker count + recent throughput.
    const grid = gridStatusFor(option.modelName);
    const descParts = [...capabilities];
    if (grid) {
      descParts.push(`${grid.count} ${grid.count === 1 ? "worker" : "workers"}`);
      if (grid.tokens_per_s != null) descParts.push(`${grid.tokens_per_s} t/s`);
    }
    const description = descParts.length > 0 ? descParts.join(" · ") : undefined;

    // Hover summary for the worker-count badge.
    const gridTooltip = grid
      ? [
          `${grid.count} online ${grid.count === 1 ? "worker" : "workers"}`,
          grid.tokens_per_s != null ? `${grid.tokens_per_s} tokens/s` : null,
          grid.avg_ttft_s != null ? `${grid.avg_ttft_s}s to first token` : null,
          grid.avg_latency_s != null ? `${grid.avg_latency_s}s avg latency` : null,
        ]
          .filter(Boolean)
          .join("\n")
      : undefined;

    return (
      <LineItemButton
        key={`${option.provider}:${option.modelName}`}
        selectVariant="select-heavy"
        state={selected ? "selected" : "empty"}
        icon={(props) => <div {...(props as any)} />}
        title={option.displayName}
        description={description}
        onClick={() => onSelect(option)}
        rightChildren={
          <div className="flex h-5 items-center gap-2">
            {grid && (
              <div
                title={gridTooltip}
                className={cn(
                  "flex items-center gap-1 rounded px-1.5 py-0.5",
                  grid.count > 0
                    ? "bg-background-neutral-03 text-text-03"
                    : "bg-background-neutral-02 text-text-04"
                )}
              >
                <SvgActivity size={12} />
                <Text font="secondary-body" color="text-03">
                  {String(grid.count)}
                </Text>
              </div>
            )}
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
