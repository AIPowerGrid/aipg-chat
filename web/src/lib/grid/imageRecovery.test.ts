import {
  parseImageReceipt,
  readImageRequests,
  recoverImageRequest,
} from "@/lib/grid/imageRecovery";

const id = "a1f092c7-d8e3-4444-8888-012345678901";

test("rejects a receipt that could escape the private content path", () => {
  expect(() =>
    parseImageReceipt({
      request_id: "../account",
      state: "completed",
      result: { model: "test" },
    })
  ).toThrow();
});

test("discards remote URLs and unrelated response metadata", () => {
  expect(
    parseImageReceipt({
      request_id: id,
      state: "completed",
      result: { model: "test", url: "https://other.test" },
      secret: "not-for-ui",
    })
  ).toEqual({ request_id: id, state: "completed", result: { model: "test" } });
});

test.each([
  null,
  {},
  { request_id: id, state: "unknown" },
  { request_id: id, state: "completed", result: null },
])("rejects malformed receipt %p", (value) => {
  expect(() => parseImageReceipt(value)).toThrow();
});

test("recovery and discovery issue authenticated same-origin GETs only", async () => {
  global.fetch = jest
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        requests: [{ request_id: id, state: "unconfirmed" }],
      }),
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({ request_id: id, state: "closed" }),
    });
  await expect(
    readImageRequests("/api/grid/images?message_id=1")
  ).resolves.toHaveLength(1);
  await expect(
    recoverImageRequest(`/api/grid/images/${id}`)
  ).resolves.toMatchObject({ state: "closed" });
  for (const [, options] of (global.fetch as jest.Mock).mock.calls) {
    expect(options).toEqual({
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      redirect: "error",
    });
  }
});

test("bounds discovery and propagates failed recovery without retry", async () => {
  global.fetch = jest
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        requests: Array(101).fill({ request_id: id, state: "closed" }),
      }),
    })
    .mockResolvedValueOnce({ ok: false });
  await expect(
    readImageRequests("/api/grid/images?message_id=1")
  ).rejects.toThrow();
  await expect(recoverImageRequest(`/api/grid/images/${id}`)).rejects.toThrow();
  expect(global.fetch).toHaveBeenCalledTimes(2);
});
