import React from "react";
import { render, screen } from "@testing-library/react";
import ChatUI, { ChatUIProps } from "@/sections/chat/ChatUI";
import { BackendMessage, Message } from "@/app/app/interfaces";
import { processRawChatHistory } from "@/app/app/services/lib";
import { GRID_FUNDING_URL } from "@/lib/grid/money";

let mockMessages: Message[] = [];
let mockSiblings: Message[] = [];
let mockError: string | null = null;
jest.mock("@/app/app/stores/useChatSessionStore", () => ({
  useCurrentMessageHistory: () => mockMessages,
  useCurrentMessageTree: () =>
    new Map([...mockMessages, ...mockSiblings].map((m) => [m.nodeId, m])),
  useUncaughtError: () => mockError,
  useLoadingError: () => null,
}));
jest.mock("@/refresh-components/popovers/llmUtils", () => ({
  buildLlmOptions: () => [],
}));
jest.mock("@/app/app/message/HumanMessage", () => ({
  __esModule: true,
  default: ({ content }: { content: string }) => <p>{content}</p>,
}));
jest.mock("@/app/app/message/messageComponents/AgentMessage", () => () => (
  <p>Answer</p>
));
jest.mock(
  "@/app/app/message/messageComponents/GridImageRecovery",
  () => () => null
);
jest.mock("@/components/chat/DynamicBottomSpacer", () => () => null);
jest.mock("@/app/app/message/MultiModelResponseView", () => ({
  __esModule: true,
  default: () => <p>Comparison panels</p>,
}));
jest.mock("@opal/components", () => ({
  Button: ({ href, children, icon: _icon, ...props }: any) =>
    href ? (
      <a href={href} {...props}>
        {children}
      </a>
    ) : (
      <button {...props}>{children}</button>
    ),
  CopyButton: () => null,
}));

const creditError = "Insufficient Grid credits. Add credits to continue.";
const raw = [
  {
    message_id: 1,
    message_type: "user",
    message: "Hello",
    parent_message: null,
    latest_child_message: 2,
    files: [],
  },
  {
    message_id: 2,
    message_type: "assistant",
    message: "Old placeholder",
    error: creditError,
    parent_message: 1,
    latest_child_message: null,
    model_display_name: "GPT-OSS-120B",
    files: [],
  },
] as unknown as BackendMessage[];
const onSubmit = jest.fn();
const onResubmit = jest.fn();
const props = {
  liveAgent: {},
  llmManager: { llmProviders: [] },
  onSubmit,
  onResubmit,
  onMessageSelection: jest.fn(),
  setPresentingDocument: jest.fn(),
  stopGenerating: jest.fn(),
  deepResearchEnabled: false,
  currentMessageFiles: [],
} as unknown as ChatUIProps;

beforeEach(() => {
  jest.clearAllMocks();
  mockError = null;
  mockSiblings = [];
  mockMessages = Array.from(processRawChatHistory(raw, []).values());
});

test("saved single-model credit error survives remount without ephemeral error state", () => {
  const first = render(<ChatUI {...props} />);
  expect(screen.getByText(creditError)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Add credits" })).toHaveAttribute(
    "href",
    GRID_FUNDING_URL
  );
  expect(screen.queryByText("Old placeholder")).not.toBeInTheDocument();
  first.unmount();
  render(<ChatUI {...props} />);
  expect(screen.getAllByRole("link", { name: "Add credits" })).toHaveLength(1);
  expect(
    screen.queryByRole("button", { name: "Regenerate" })
  ).not.toBeInTheDocument();
  expect(onSubmit).not.toHaveBeenCalled();
  expect(onResubmit).not.toHaveBeenCalled();
});

test("live error is not duplicated by the global banner", () => {
  mockError = creditError;
  render(<ChatUI {...props} />);
  expect(screen.getAllByText(creditError)).toHaveLength(1);
});

test("older failed turn stays visible after a subsequent user message", () => {
  mockMessages.push({
    nodeId: 3,
    messageId: 3,
    message: "Another question",
    type: "user",
    files: [],
    parentNodeId: 2,
    childrenNodeIds: [],
    latestChildNodeId: null,
    toolCall: null,
    packets: [],
  });
  render(<ChatUI {...props} />);
  expect(screen.getByText(creditError)).toBeInTheDocument();
  expect(onResubmit).not.toHaveBeenCalled();
});

test("failure before an assistant message exists still shows funding", () => {
  mockMessages = mockMessages.slice(0, 1);
  mockError = creditError;
  render(<ChatUI {...props} />);
  expect(screen.getByRole("link", { name: "Add credits" })).toBeInTheDocument();
});

test("comparison errors stay in their panels, not a duplicate global banner", () => {
  mockMessages[0]!.childrenNodeIds = [2, 3];
  mockSiblings.push({
    ...mockMessages[1]!,
    nodeId: 3,
    messageId: 3,
    modelDisplayName: "Other model",
  });
  render(<ChatUI {...props} />);
  expect(screen.getByText("Comparison panels")).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Add credits" })
  ).not.toBeInTheDocument();
});

test("generic saved failure is visible without a funding link or automatic retry", () => {
  mockMessages[1]!.message = "Model encountered an error during generation.";
  render(<ChatUI {...props} />);
  expect(screen.getByText(mockMessages[1]!.message)).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Add credits" })
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Regenerate" })
  ).toBeInTheDocument();
  expect(onResubmit).not.toHaveBeenCalled();
});
