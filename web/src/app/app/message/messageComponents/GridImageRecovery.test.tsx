import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import GridImageRecovery from "@/app/app/message/messageComponents/GridImageRecovery";

let mockUser: { id: string; is_anonymous_user?: boolean } | null = {
  id: "owner",
};
jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({ user: mockUser }),
}));
jest.mock("@opal/components", () => ({
  Button: ({ children, icon: _icon, tooltip, href, ...props }: any) =>
    href ? (
      <a href={href} aria-label={tooltip} {...props}>
        {children}
      </a>
    ) : (
      <button aria-label={tooltip} {...props}>
        {children}
      </button>
    ),
}));

const id = "a1f092c7-d8e3-4444-8888-012345678901";
const pending = { request_id: id, state: "unconfirmed", result: null };
const completed = {
  ...pending,
  state: "completed",
  result: { model: "Krea 2 Turbo" },
};
const json = (value: unknown) => ({ ok: true, json: async () => value });

function view(props = {}) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <GridImageRecovery messageId={1} {...props} />
    </SWRConfig>
  );
}

beforeEach(() => {
  mockUser = { id: "owner" };
  global.IntersectionObserver = class {
    constructor(private callback: (entries: unknown[]) => void) {}
    observe() {
      this.callback([{ isIntersecting: true }]);
    }
    disconnect() {}
  } as unknown as typeof IntersectionObserver;
  global.fetch = jest
    .fn()
    .mockImplementation(async (url: string) =>
      url.includes("?message_id=")
        ? json({ requests: [pending] })
        : json(completed)
    );
});

test("reload discovers the original receipt and never submits a generation", async () => {
  const first = view();
  expect(await screen.findByAltText("Recovered image 1")).toHaveAttribute(
    "src",
    `/api/grid/images/${id}/content?revision=0`
  );
  first.unmount();
  view();
  expect(await screen.findByAltText("Recovered image 1")).toBeInTheDocument();
  for (const [url, options] of (global.fetch as jest.Mock).mock.calls) {
    expect(url).toMatch(/^\/api\/grid\/images/);
    expect(options.method).toBe("GET");
    expect(options).not.toHaveProperty("body");
  }
  expect(
    screen.getByRole("link", { name: "Download original image" })
  ).toHaveAttribute("href", `/api/grid/images/${id}/content?download=true`);
});

test("failed recovery stays unconfirmed and retry reads the same receipt", async () => {
  (global.fetch as jest.Mock).mockImplementation(async (url: string) =>
    url.includes("?message_id=") ? json({ requests: [pending] }) : { ok: false }
  );
  view();
  await screen.findByText("The original image is temporarily unavailable.");
  expect(screen.getByText(/Image status is unconfirmed/)).toBeInTheDocument();
  (global.fetch as jest.Mock).mockImplementation(async () => json(completed));
  fireEvent.click(screen.getByRole("button", { name: "Check original image" }));
  await screen.findByAltText("Recovered image 1");
  expect((global.fetch as jest.Mock).mock.lastCall[0]).toBe(
    `/api/grid/images/${id}`
  );
});

test("a failed asset can be reloaded without generating another image", async () => {
  view();
  fireEvent.error(await screen.findByAltText("Recovered image 1"));
  fireEvent.click(screen.getByRole("button", { name: "Check original image" }));
  await waitFor(() =>
    expect(screen.getByAltText("Recovered image 1")).toHaveAttribute(
      "src",
      `/api/grid/images/${id}/content?revision=1`
    )
  );
  expect(
    (global.fetch as jest.Mock).mock.calls.every(
      ([, options]) => options.method === "GET"
    )
  ).toBe(true);
});

test.each([null, { id: "anonymous", is_anonymous_user: true }])(
  "no receipt discovery without an authenticated account %p",
  (user) => {
    mockUser = user;
    view();
    expect(global.fetch).not.toHaveBeenCalled();
  }
);

test("already displayed successful images are not duplicated", async () => {
  (global.fetch as jest.Mock).mockImplementation(async (url: string) =>
    url.includes("?message_id=")
      ? json({ requests: [completed] })
      : json(completed)
  );
  view({ displayedImageCount: 1 });
  await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
  expect(
    screen.queryByRole("region", { name: "Image requests" })
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Original images" }));
  await screen.findByAltText("Recovered image 1");
});

test("closed receipts do not claim a refund or show an image", async () => {
  (global.fetch as jest.Mock).mockImplementation(async (url: string) =>
    url.includes("?message_id=")
      ? json({ requests: [pending] })
      : json({ ...pending, state: "closed" })
  );
  view();
  await screen.findByText("No image was saved for this request.");
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

test("switching accounts never reuses the previous account's receipts", async () => {
  const cache = new Map();
  const tree = () => (
    <SWRConfig value={{ provider: () => cache }}>
      <GridImageRecovery messageId={1} />
    </SWRConfig>
  );
  const rendered = render(tree());
  await screen.findByAltText("Recovered image 1");
  mockUser = { id: "different-owner" };
  (global.fetch as jest.Mock).mockResolvedValue(json({ requests: [] }));
  rendered.rerender(tree());
  expect(screen.queryByAltText("Recovered image 1")).not.toBeInTheDocument();
  await waitFor(() =>
    expect((global.fetch as jest.Mock).mock.calls.length).toBeGreaterThan(2)
  );
});
