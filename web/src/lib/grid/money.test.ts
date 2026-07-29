import { formatGridUSD } from "@/lib/grid/money";

describe("formatGridUSD", () => {
  it("preserves sub-cent credit values", () => {
    expect(formatGridUSD(0.0049)).toBe("$0.0049");
    expect(formatGridUSD(0.012)).toBe("$0.012");
  });

  it("keeps ordinary balances compact", () => {
    expect(formatGridUSD(0)).toBe("$0.00");
    expect(formatGridUSD(12.5)).toBe("$12.50");
  });
});
