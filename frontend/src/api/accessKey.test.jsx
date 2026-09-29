import { act, fireEvent, render, screen } from "@testing-library/react";
import axios from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import AccessKeyPrompt from "../components/ui/AccessKeyPrompt";
import { authHeaders, getAccessKey, reportAccessDenied, setAccessKey } from "./accessKey";

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("API client with a hosted backend's access key", () => {
  async function clientWith(adapter) {
    vi.resetModules();
    const previous = axios.defaults.adapter;
    axios.defaults.adapter = adapter;
    try {
      return await import("./client");
    } finally {
      axios.defaults.adapter = previous;
    }
  }

  it("sends the stored key as a bearer token", async () => {
    setAccessKey("s3cret");
    const adapter = vi.fn(async (config) => ({ data: { document_id: "doc_1" }, status: 200, headers: {}, config }));
    const { getDocument } = await clientWith(adapter);
    await getDocument("doc_1");
    expect(adapter.mock.calls[0][0].headers.Authorization).toBe("Bearer s3cret");
  });

  it("reports a 401 so the key can be requested", async () => {
    const adapter = vi.fn(async (config) => {
      const error = new Error("Unauthorized");
      error.config = config;
      error.response = { status: 401, data: { detail: "A valid access key is required." }, config };
      throw error;
    });
    const { getDocument } = await clientWith(adapter);
    const { onAccessDenied } = await import("./accessKey");
    const denied = vi.fn();
    onAccessDenied(denied);
    await expect(getDocument("doc_1")).rejects.toBeTruthy();
    expect(denied).toHaveBeenCalledTimes(1);
  });
});

describe("AccessKeyPrompt", () => {
  it("opens on a 401 and stores the entered key before reloading", () => {
    const reload = vi.fn();
    vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, reload });
    render(<AccessKeyPrompt />);
    expect(screen.queryByText("Access key required")).toBeNull();

    act(() => reportAccessDenied());
    fireEvent.change(screen.getByLabelText("Access key"), { target: { value: " s3cret " } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(getAccessKey()).toBe("s3cret");
    expect(authHeaders()).toEqual({ Authorization: "Bearer s3cret" });
    expect(reload).toHaveBeenCalled();
  });
});

it("opens the prompt for a 401 reported before it mounted", async () => {
  vi.resetModules();
  const accessKey = await import("./accessKey");
  const { default: Prompt } = await import("../components/ui/AccessKeyPrompt");
  accessKey.reportAccessDenied();
  render(<Prompt />);
  expect(screen.getByText("Access key required")).toBeTruthy();
});
