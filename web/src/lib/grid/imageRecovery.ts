import { GridImageReceipt } from "@/lib/grid/interfaces";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function parseImageReceipt(value: unknown): GridImageReceipt {
  if (!value || typeof value !== "object")
    throw new Error("Invalid image receipt");
  const receipt = value as Partial<GridImageReceipt>;
  if (
    typeof receipt.request_id !== "string" ||
    !UUID_PATTERN.test(receipt.request_id) ||
    !["unconfirmed", "completed", "closed"].includes(receipt.state ?? "") ||
    (receipt.state === "completed" &&
      (!receipt.result || typeof receipt.result.model !== "string"))
  ) {
    throw new Error("Invalid image receipt");
  }
  return {
    request_id: receipt.request_id,
    state: receipt.state as GridImageReceipt["state"],
    result:
      receipt.state === "completed" ? { model: receipt.result!.model } : null,
  };
}

async function readJSON(url: string): Promise<unknown> {
  const response = await fetch(url, {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
  });
  if (!response.ok) throw new Error("Image recovery is unavailable");
  return response.json();
}

export async function readImageRequests(
  url: string
): Promise<GridImageReceipt[]> {
  const value = (await readJSON(url)) as { requests?: unknown } | null;
  if (!value || !Array.isArray(value.requests) || value.requests.length > 100) {
    throw new Error("Invalid image request list");
  }
  return value.requests.map(parseImageReceipt);
}

export async function recoverImageRequest(
  url: string
): Promise<GridImageReceipt> {
  return parseImageReceipt(await readJSON(url));
}
