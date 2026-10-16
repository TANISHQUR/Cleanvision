// Thin wrapper around fetch that adds the login token and turns errors into readable messages.
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "cleanvision_token";
const USER_KEY = "cleanvision_user";

export const session = {
  get token() {
    return localStorage.getItem(TOKEN_KEY);
  },
  get user() {
    return localStorage.getItem(USER_KEY);
  },
  save(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, user);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (session.token) headers.Authorization = `Bearer ${session.token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { method, headers, body: payload });
  } catch {
    throw new ApiError("Can't reach the CleanVision server. Check that the backend is running on port 8000.", 0);
  }
  if (res.status === 401 && !path.endsWith("/auth/login")) {
    session.clear();
    window.dispatchEvent(new Event("cleanvision:logout"));
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    let msg = data?.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join(", ");
    throw new ApiError(msg || `Request failed (${res.status})`, res.status);
  }
  return data;
}

export const api = {
  login: (username, password) => request("/api/auth/login", { method: "POST", body: { username, password } }),
  stats: () => request("/api/stats"),
  violations: (params = {}) => request(`/api/violations?${new URLSearchParams(clean(params))}`),
  violation: (id) => request(`/api/violations/${id}`),
  review: (id, body) => request(`/api/violations/${id}/review`, { method: "POST", body }),
  citizens: (q = "") => request(`/api/citizens?${new URLSearchParams({ q })}`),
  citizen: (id) => request(`/api/citizens/${id}`),
  challans: (status) => request(`/api/challans${status ? `?status=${status}` : ""}`),
  updateChallan: (id, status) => request(`/api/challans/${id}`, { method: "PATCH", body: { status } }),
  jobs: () => request("/api/jobs"),
  uploadVideo: (form) => request("/api/jobs", { method: "POST", form }),
};

export function mediaUrl(path) {
  if (!path) return null;
  return `${API_BASE}${path}?token=${encodeURIComponent(session.token || "")}`;
}

function clean(obj) {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== ""));
}
