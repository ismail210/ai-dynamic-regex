import { afterEach, describe, expect, it, vi } from "vitest";
import { checkBackendIdentity, compareIdentity, EXPECTED_SUMMARY_API } from "./devIdentity";

const expected = {
  worktree: "C:\\Users\\dev\\wt-sri",
  revision: "e0fd0c6aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  proxy_target: "http://127.0.0.1:8000",
};
const paired = { ...expected, summary_api: EXPECTED_SUMMARY_API };

describe("compareIdentity", () => {
  it("accepts the same worktree regardless of path case and separators", () => {
    expect(compareIdentity(expected, { ...paired, worktree: "c:/users/dev/wt-sri/" })).toEqual({
      ok: true,
    });
  });

  it("rejects a backend from another worktree and names both", () => {
    const result = compareIdentity(expected, {
      ...paired,
      worktree: "C:\\Users\\dev\\git\\ai-dynamic-regex-integration",
    });
    expect(result.ok).toBe(false);
    expect(result.problem).toContain("ai-dynamic-regex-integration");
    expect(result.problem).toContain("wt-sri");
    expect(result.problem).toContain("http://127.0.0.1:8000");
  });

  it("rejects a backend serving an older summary API", () => {
    const result = compareIdentity(expected, { ...paired, summary_api: "drawing_intelligence_v1" });
    expect(result.ok).toBe(false);
    expect(result.problem).toContain("drawing_intelligence_v1");
  });

  it("warns without blocking when only the startup revision differs", () => {
    const result = compareIdentity(expected, { ...paired, revision: "700c72fbbbbbbbbbbbbbbbbb" });
    expect(result.ok).toBe(true);
    expect(result.warning).toContain("700c72f");
  });
});

it("is a no-op outside the Vite dev server", async () => {
  await expect(checkBackendIdentity()).resolves.toEqual({ ok: true });
});

describe("checkBackendIdentity under the dev server", () => {
  async function load(fetchImpl) {
    vi.resetModules();
    vi.stubGlobal("__DEV_PAIR__", expected);
    vi.stubGlobal("fetch", vi.fn(fetchImpl));
    return import("./devIdentity");
  }
  const respond = (body) => async () => ({ ok: true, status: 200, json: async () => body });

  afterEach(() => vi.unstubAllGlobals());

  it("reuses a passing check for reads but re-checks every write", async () => {
    const identity = await load(respond(paired));
    await identity.checkBackendIdentity({ fresh: false });
    await identity.checkBackendIdentity({ fresh: false });
    expect(fetch).toHaveBeenCalledTimes(1);
    await identity.checkBackendIdentity();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("never reuses a failed check and notifies listeners only on change", async () => {
    const identity = await load(async () => ({ ok: false, status: 404 }));
    const listener = vi.fn();
    identity.onBackendIdentity(listener);
    const first = await identity.checkBackendIdentity({ fresh: false });
    await identity.checkBackendIdentity({ fresh: false });
    expect(first.ok).toBe(false);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
