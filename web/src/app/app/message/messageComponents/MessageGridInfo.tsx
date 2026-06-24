"use client";

import { SelectButton } from "@opal/components";
import { SvgInfo } from "@opal/icons";

import SimplePopover from "@/refresh-components/SimplePopover";
import Text from "@/refresh-components/texts/Text";
import useGridModelStatus from "@/hooks/useGridModelStatus";

interface MessageGridInfoProps {
  modelName: string;
}

/**
 * AIPG fork: per-message ⓘ popover. Shows which model produced the reply and
 * that model's current AI Power Grid performance (tokens/sec, TTFT, latency,
 * online worker count) from the grid-status proxy. These are model-level live
 * stats — not the exact worker for this specific message — which avoids
 * threading provenance through Onyx's streaming pipeline.
 */
export default function MessageGridInfo({ modelName }: MessageGridInfoProps) {
  const { models } = useGridModelStatus();

  // Match the message's model against the grid's text models (case-insensitive,
  // tolerate a provider-prefixed name like "AI Power Grid/gpt-oss-120b").
  const lower = modelName.toLowerCase();
  const stat = models.find(
    (m) =>
      m.type === "text" &&
      (m.name.toLowerCase() === lower || lower.endsWith(m.name.toLowerCase()))
  );

  return (
    <SimplePopover
      side="top"
      align="end"
      width="lg"
      trigger={
        <SelectButton
          icon={SvgInfo}
          variant="select-light"
          state="empty"
          tooltip="Generation details"
          data-testid="AgentMessage/grid-info-button"
        />
      }
    >
      {/* Stacked rows + full-width wrapping values so long worker/model names
          are never clipped. */}
      <div className="p-3 w-full flex flex-col gap-3">
        <Text text02 mainUiAction>
          Generation details
        </Text>
        <div className="flex flex-col gap-2.5">
          <Row label="Model" value={modelName} />
          {stat ? (
            <>
              <Row
                label="Served by"
                value={`${stat.count} grid worker${stat.count === 1 ? "" : "s"}`}
              />
              <Row
                label="Throughput"
                value={stat.tokens_per_s != null ? `${stat.tokens_per_s} tokens/sec` : "—"}
              />
              <Row
                label="Time to first token"
                value={stat.avg_ttft_s != null ? `${stat.avg_ttft_s}s` : "—"}
              />
              <Row
                label="Avg latency"
                value={stat.avg_latency_s != null ? `${stat.avg_latency_s}s` : "—"}
              />
            </>
          ) : (
            <Text text04 secondaryBody>
              Live grid stats unavailable for this model.
            </Text>
          )}
        </div>
        <Text text05 secondaryBody>
          Recent grid averages (last 24h), via AI Power Grid.
        </Text>
      </div>
    </SimplePopover>
  );
}

interface RowProps {
  label: string;
  value: string;
}

function Row({ label, value }: RowProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <Text text04 secondaryBody>
        {label}
      </Text>
      <Text text01 mainUiBody className="break-words">
        {value}
      </Text>
    </div>
  );
}
