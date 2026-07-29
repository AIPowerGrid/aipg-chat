import type { GridTextQuote } from "@/lib/grid/interfaces";

export function gridQuoteIsUnpriced(quote: GridTextQuote | null): boolean {
  return Boolean(quote?.charging_enabled && !quote.estimate.priced);
}

export function gridQuoteNeedsFunding(quote: GridTextQuote | null): boolean {
  return Boolean(
    quote?.charging_enabled &&
    quote.estimate.priced &&
    !quote.estimate.balance_sufficient
  );
}

export function gridQuoteBlocksGeneration(
  quote: GridTextQuote | null
): boolean {
  return gridQuoteIsUnpriced(quote) || gridQuoteNeedsFunding(quote);
}

export function isGridCreditError(error: string): boolean {
  return /insufficient (?:grid )?credits?|payment required/i.test(error);
}
