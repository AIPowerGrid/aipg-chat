import { renderHook, waitFor } from "@testing-library/react";
import useChatSessionController from "@/hooks/useChatSessionController";

const mockUpdate = jest.fn();
let mockHistory: unknown[] = [];
let mockChatState = "input";
const mockNoop = jest.fn();
const mockStore = {
  updateSessionAndMessageTree: mockUpdate,
  updateSessionMessageTree: mockNoop,
  setIsFetchingChatMessages: mockNoop,
  setCurrentSession: mockNoop,
  initializeSession: mockNoop,
  updateCurrentChatSessionSharedStatus: mockNoop,
  updateCurrentSelectedNodeForDocDisplay: mockNoop,
  get sessions() {
    return new Map([["session", { chatState: mockChatState }]]);
  },
  currentSessionId: "session",
};
jest.mock("@/app/app/stores/useChatSessionStore", () => ({
  useChatSessionStore: (selector: (store: unknown) => unknown) =>
    selector(mockStore),
  useCurrentMessageHistory: () => mockHistory,
}));
jest.mock("@/lib/hooks/useForcedTools", () => ({
  useForcedTools: () => ({ setForcedToolIds: mockNoop }),
}));
jest.mock("@/app/app/projects/projectsService", () => ({
  getSessionProjectTokenCount: async () => 0,
  getProjectFilesForSession: async () => [],
}));

const error = "Insufficient Grid credits. Add credits to continue.";
function props() {
  return {
    existingChatSessionId: "session",
    searchParams: new URLSearchParams(),
    filterManager: {},
    setSelectedAgentFromId: mockNoop,
    setSelectedDocuments: mockNoop,
    setCurrentMessageFiles: mockNoop,
    chatSessionIdRef: { current: null },
    loadedIdSessionRef: { current: null },
    chatInputBarRef: { current: null },
    isInitialLoad: { current: true },
    submitOnLoadPerformed: { current: false },
    refreshChatSessions: mockNoop,
    onSubmit: mockNoop,
  } as unknown as Parameters<typeof useChatSessionController>[0];
}

beforeEach(() => {
  jest.clearAllMocks();
  mockHistory = [];
  mockChatState = "input";
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      chat_session_id: "session",
      persona_id: 0,
      description: "Credit test",
      packets: [],
      messages: [
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
          message: error,
          error,
          parent_message: 1,
          latest_child_message: null,
          files: [],
        },
      ],
    }),
  });
});

test("cold reload hydrates saved error even with no previous loaded-session ref", async () => {
  const input = props();
  renderHook(() => useChatSessionController(input));
  await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
  expect(mockUpdate.mock.calls[0]![1].get(2)).toMatchObject({
    type: "error",
    message: error,
  });
  expect(mockNoop.mock.calls).not.toContainEqual([
    expect.objectContaining({ message: "Hello" }),
  ]);
  expect(global.fetch).toHaveBeenCalledTimes(1);
  expect((global.fetch as jest.Mock).mock.calls[0]).toEqual([
    "/api/chat/get-chat-session/session",
  ]);
});

test("first-turn renaming preserves a live error already in memory", async () => {
  mockHistory = [{ type: "error", message: error }];
  const input = props();
  renderHook(() => useChatSessionController(input));
  await waitFor(() => expect(mockNoop).toHaveBeenCalledWith(0));
  expect(mockUpdate).not.toHaveBeenCalled();
});

test("active stream is not overwritten by a history reload", () => {
  mockChatState = "streaming";
  const input = props();
  renderHook(() => useChatSessionController(input));
  expect(global.fetch).not.toHaveBeenCalled();
  expect(mockUpdate).not.toHaveBeenCalled();
});
