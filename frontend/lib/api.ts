export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
let csrf = "";
export function setCsrf(value: string) { csrf = value; }
export async function apiFetch(path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  headers.set("X-Request-ID", crypto.randomUUID());
  if (!["GET", "HEAD"].includes(options.method ?? "GET") && csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(API_URL + path, { ...options, headers, credentials: "include" });
  if (response.status === 401 && path !== "/auth/login" && path !== "/auth/me") window.dispatchEvent(new Event("rag-signout"));
  return response;
}
export async function responseError(response: Response) {
  try { const data = await response.json(); return typeof data.detail === "string" ? data.detail : `Request failed (${response.status}).`; }
  catch { return `Request failed (${response.status}).`; }
}
export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await apiFetch(path, { method, ...(body === undefined ? {} :
    { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }) });
  if (!response.ok) throw new Error(await responseError(response));
  return response.json();
}
