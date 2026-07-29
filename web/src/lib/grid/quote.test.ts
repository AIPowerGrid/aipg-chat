import type { GridTextQuote } from "@/lib/grid/interfaces";
import {
  gridQuoteBlocksGeneration,
  gridQuoteIsUnpriced,
  gridQuoteNeedsFunding,
  isGridCreditError,
} from "@/lib/grid/quote";

function quote({
  charging = true,
  priced = true,
  sufficient = true,
}: {
  charging?: boolean;
  priced?: boolean;
  sufficient?: boolean;
} = {}): GridTextQuote {
  return {
    account_id: "account-1",
    promotional: { remaining_usd: 0, active: false },
    free: { remaining_usd: 0, active: false },
    paid: { balance_usd: 0.02 },
    total_spendable_usd: 0.02,
    charging_enabled: charging,
    charging_mode: charging ? "on" : "off",
    estimate: {
      model: "gpt-oss-120b",
      modality: "text",
      priced,
      reason: priced ? null : "unpriced",
      cost_usd: priced ? 0.0049 : null,
      balance_sufficient: sufficient,
      prompt_tokens: 12,
      max_tokens: 32768,
      shortfall_micro: sufficient ? 0 : 1000,
    },
  };
}

describe("Grid text quote decisions", () => {
  it("does not block preview mode even when the preview exceeds the balance", () => {
    expect(
      gridQuoteBlocksGeneration(quote({ charging: false, sufficient: false }))
    ).toBe(false);
  });

  it("blocks unpriced work when charging is active", () => {
    const value = quote({ priced: false, sufficient: false });
    expect(gridQuoteIsUnpriced(value)).toBe(true);
    expect(gridQuoteBlocksGeneration(value)).toBe(true);
  });

  it("links priced but insufficient work to funding", () => {
    const value = quote({ sufficient: false });
    expect(gridQuoteNeedsFunding(value)).toBe(true);
    expect(gridQuoteBlocksGeneration(value)).toBe(true);
  });

  it("allows sufficiently funded priced work", () => {
    expect(gridQuoteBlocksGeneration(quote())).toBe(false);
  });

  it("recognizes reservation failures that need funding", () => {
    expect(isGridCreditError("Insufficient Grid credits")).toBe(true);
    expect(isGridCreditError("402 Payment Required")).toBe(true);
    expect(isGridCreditError("Worker timed out")).toBe(false);
  });
});
