import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, tokenStore } from "./api";

describe("API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    tokenStore.clear();
  });

  it("sends the bearer token to authenticated endpoints", async () => {
    tokenStore.set("signed-token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.projects();

    const options = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(options.headers).get("Authorization")).toBe("Bearer signed-token");
  });

  it("clears stale credentials on unauthorised responses", async () => {
    tokenStore.set("expired");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Expired" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(api.projects()).rejects.toEqual(new ApiError(401, "Expired"));
    expect(tokenStore.get()).toBeNull();
  });
});
