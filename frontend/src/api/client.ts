import type { z } from "zod";
import { API_BASE_URL } from "@/lib/config";

// Typed error: backend returns { detail: string }; map status + detail to a
// friendly message. `message` (Error.message) is what TanStack Query surfaces;
// `detail`/`status` stay available for richer UI later.
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(ApiError.friendly(status, detail));
    this.name = "ApiError";
  }

  static friendly(status: number, detail: string): string {
    switch (status) {
      case 404:
        return "Not found.";
      case 409:
        return "This book isn't ready yet.";
      case 413:
        return "That file is too large.";
      case 422:
        return detail || "Invalid request.";
      default:
        return detail || `Request failed (${status}).`;
    }
  }
}

// The one fetch wrapper. Base URL from config, JSON in/out, zod-parse on
// success, throw ApiError on non-2xx or shape mismatch. No axios. Works
// from client components today; the same wrapper is where a session header /
// cookie pass-through lands when auth arrives.
export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  // Only declare a JSON content-type when we actually send a JSON body: a GET
  // needs none, and multipart/FormData (upload) must keep the
  // browser-set content-type so its boundary survives.
  const headers = new Headers(init?.headers);
  if (
    init?.body != null &&
    !(init.body instanceof FormData) &&
    !headers.has("content-type")
  ) {
    headers.set("content-type", "application/json");
  }

  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body — keep statusText */
    }
    throw new ApiError(res.status, detail);
  }

  // 204 No Content (e.g. DELETE) has no body to parse — validate against
  // the caller's schema (pass z.void() there) instead of calling res.json().
  const parsed =
    res.status === 204
      ? schema.safeParse(undefined)
      : schema.safeParse(await res.json());
  if (!parsed.success) {
    // Backend drift / unexpected shape — surface, don't return a silent `any`.
    throw new ApiError(res.status, `Unexpected response shape: ${parsed.error.message}`);
  }
  return parsed.data;
}
