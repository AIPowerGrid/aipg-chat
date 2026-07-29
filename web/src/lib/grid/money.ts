export const GRID_FUNDING_URL =
  "https://console.aipowergrid.io/dashboard/funding?returnTo=https%3A%2F%2Faipg.chat%2Fapp";

export function formatGridUSD(value = 0): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: value > 0 && value < 0.01 ? 4 : 3,
  }).format(value);
}
