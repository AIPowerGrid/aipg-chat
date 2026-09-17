import { fireEvent, render, screen } from "@testing-library/react";
import { ErrorBanner } from "@/app/app/message/Resubmit";
import { GRID_FUNDING_URL } from "@/lib/grid/money";

describe("Chat credit and failure recovery", () => {
  it.each([
    "Insufficient Grid credits",
    "litellm.APIError: OpenAIException - Error code: 402 - {'detail': 'insufficient credits'}",
    "402 Payment Required",
  ])("offers funding instead of regeneration for %s", (error) => {
    const resubmit = jest.fn();
    render(<ErrorBanner error={error} resubmit={resubmit} />);

    expect(screen.getByRole("alert")).toHaveTextContent(error);
    expect(screen.getByRole("link", { name: "Add credits" })).toHaveAttribute(
      "href",
      GRID_FUNDING_URL
    );
    expect(screen.queryByRole("button", { name: "Regenerate" })).toBeNull();
    expect(resubmit).not.toHaveBeenCalled();
  });

  it("keeps funding available when the server marks the rejection non-retryable", () => {
    render(<ErrorBanner error="insufficient credits" isRetryable={false} />);
    expect(screen.getByRole("link", { name: "Add credits" })).toBeVisible();
  });

  it("requires an explicit click to retry a worker failure", () => {
    const resubmit = jest.fn();
    render(
      <ErrorBanner
        error="Worker timed out"
        errorCode="SERVICE_UNAVAILABLE"
        details={{ model: "gpt-oss-120b", provider: "openai_compatible" }}
        resubmit={resubmit}
      />
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Worker timed out");
    expect(screen.getByRole("alert")).toHaveTextContent("gpt-oss-120b");
    expect(screen.queryByRole("link", { name: "Add credits" })).toBeNull();
    expect(resubmit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));
    expect(resubmit).toHaveBeenCalledTimes(1);
  });

  it("does not offer retry or funding for a non-retryable authentication failure", () => {
    render(
      <ErrorBanner
        error="Sign in to continue"
        errorCode="AUTH_ERROR"
        isRetryable={false}
        resubmit={jest.fn()}
      />
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Sign in to continue");
    expect(screen.queryByRole("button", { name: "Regenerate" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Add credits" })).toBeNull();
  });
});
