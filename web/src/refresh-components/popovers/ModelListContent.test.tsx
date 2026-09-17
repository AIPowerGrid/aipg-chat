import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import ModelListContent from "./ModelListContent";
import useGridModelStatus from "@/hooks/useGridModelStatus";
import type { GridModelStatus } from "@/lib/grid/interfaces";
import { makeProvider } from "@tests/setup/llmProviderTestUtils";

jest.mock("@/hooks/useGridModelStatus");
jest.mock("@/hooks/useGridWorkers", () => ({
  __esModule: true,
  default: () => ({ workers: [], isLoading: false }),
}));
jest.mock("@opal/components", () => ({
  ...jest.requireActual("@opal/components"),
  PopoverMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineItemButton: ({
    title,
    rightChildren,
  }: {
    title: string;
    rightChildren: ReactNode;
  }) => (
    <div>
      {title}
      {rightChildren}
    </div>
  ),
  Tooltip: ({
    tooltip,
    children,
  }: {
    tooltip: ReactNode;
    children: ReactNode;
  }) => (
    <>
      {children}
      <div role="tooltip">{tooltip}</div>
    </>
  ),
}));

const model: GridModelStatus = {
  name: "new-community-model",
  type: "text",
  count: 1,
  tokens_per_s: null,
  avg_ttft_s: null,
  avg_latency_s: null,
  samples: 0,
  max_context_length: 8192,
};

function renderPicker(pricing?: GridModelStatus["pricing"]) {
  jest.mocked(useGridModelStatus).mockReturnValue({
    models: [{ ...model, pricing }],
    isLoading: false,
    error: undefined,
    refetch: jest.fn(),
  });
  return render(
    <ModelListContent
      llmProviders={[
        makeProvider({
          model_configurations: [
            {
              name: model.name,
              is_visible: true,
              max_input_tokens: null,
              supports_image_input: false,
              supports_reasoning: false,
            },
          ],
        }),
      ]}
      onSelect={jest.fn()}
      isSelected={() => false}
    />
  );
}

test.each(["default", "model"] as const)(
  "displays the %s tariff supplied by Core",
  (source) => {
    renderPicker({
      currency: "USD",
      input_per_mtok_usd: 0.075,
      output_per_mtok_usd: 0.3,
      source,
      version: "2026-09-17-a",
    });
    expect(screen.getByText("Input / 1M tokens")).toBeInTheDocument();
    expect(screen.getByText("$0.075")).toBeInTheDocument();
    expect(screen.getByText("$0.3")).toBeInTheDocument();
    expect(
      screen.getByText(source === "default" ? "Standard" : "Model-specific")
    ).toBeInTheDocument();
  }
);

test.each([undefined, null])(
  "does not invent a free price for missing metadata (%s)",
  (pricing) => {
    renderPicker(pricing);
    expect(screen.queryByText("Input / 1M tokens")).not.toBeInTheDocument();
    expect(screen.queryByText("$0")).not.toBeInTheDocument();
    expect(screen.getByText("1 online worker")).toBeInTheDocument();
  }
);
