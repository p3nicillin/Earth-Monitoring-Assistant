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

  it("sends login credentials as URL-encoded form data", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ access_token: "token", token_type: "bearer", user: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.login("analyst@example.com", "ChangeMe123!");

    const options = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(options.headers).get("Content-Type")).toBe(
      "application/x-www-form-urlencoded",
    );
    expect(String(options.body)).toBe(
      "username=analyst%40example.com&password=ChangeMe123%21",
    );
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

  it("renders structured validation errors as readable messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: [{ msg: "Field required" }] }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(api.projects()).rejects.toEqual(new ApiError(422, "Field required"));
  });
});
