/** Tiny fetch wrapper. Always sends cookies so the session round-trips. */

const BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API ${status}`);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      // ignore parse errors — error body is best-effort
    }
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export type Me = {
  user_id: string;
  org_id: string;
  email: string;
  name: string;
  role: "org_admin" | "ops_lead" | "site_manager" | "viewer";
};

export const api = {
  me: () => request<Me>("/auth/me"),
  login: (email: string, password: string, org_id: string) =>
    request<void>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, org_id }),
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
};
