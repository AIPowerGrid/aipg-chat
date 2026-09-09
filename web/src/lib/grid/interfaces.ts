/**
 * AIPG fork: shapes returned by the grid status proxy
 * (`/api/grid/workers`, `/api/grid/models`). These mirror the AI Power Grid's
 * `/v1/workers` and `/v1/status/models` responses, fetched server-side by
 * `backend/onyx/server/manage/llm/grid_status.py`.
 */

export interface GridWorker {
  id: string;
  name: string;
  models: string[];
  job_types: string[];
  online: boolean;
}

export interface GridWorkersResponse {
  count: number;
  workers: GridWorker[];
}

export interface GridModelStatus {
  name: string;
  count: number; // workers currently serving this model
  type: string; // "text" | "image" | "video"
  // Recent performance (last 24h) — null until samples exist. t/s + ttft are
  // text-meaningful; media reports latency only.
  tokens_per_s: number | null;
  avg_ttft_s: number | null;
  avg_latency_s: number | null;
  samples: number;
  // Largest context window (in tokens) advertised by workers serving this
  // model — auto-detected per backend (vLLM max_model_len, etc.). null until a
  // worker reports it.
  max_context_length: number | null;
}

export interface GridAccountSummary {
  account_id: string;
  paid_balance_usd: number;
  promotional_balance_usd: number;
  promotional_active: boolean;
  daily_balance_usd: number;
  daily_active: boolean;
  total_spendable_usd: number;
  total_preview_usd: number;
  charging_enabled: boolean;
  charging_mode: "off" | "allowlist" | "on";
}

export interface GridTextQuote {
  account_id: string;
  promotional: {
    remaining_usd: number;
    active: boolean;
  };
  free: {
    remaining_usd: number;
    active: boolean;
  };
  paid: {
    balance_usd: number;
  };
  total_spendable_usd: number;
  charging_enabled: boolean;
  charging_mode: "off" | "allowlist" | "on";
  estimate: {
    model: string;
    modality: "text";
    priced: boolean;
    reason: string | null;
    cost_usd: number | null;
    balance_sufficient: boolean;
    prompt_tokens: number;
    max_tokens: number;
    shortfall_micro: number | null;
  };
}

export interface GridImageReceipt {
  request_id: string;
  state: "unconfirmed" | "completed" | "closed";
  result: { model: string } | null;
}
