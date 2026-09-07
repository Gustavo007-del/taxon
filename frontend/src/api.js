// Thin fetch() wrapper around the existing DRF API (/api/...).
// Same contract as the classic review_ui/app.js: JSON in/out, CSRF header
// on non-GET requests (cookie is set by Django's ensure_csrf_cookie).

function getCookie(name) {
  const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    headers.set("X-CSRFToken", getCookie("csrftoken") || "");
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const err = await response.json();
      message = err.detail || JSON.stringify(err);
    } catch {
      // non-JSON error body; keep the status-based message
    }
    throw new Error(message);
  }
  return response.json();
}

export const api = {
  stats: () => apiFetch("/api/stats/"),

  results: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        qs.set(key, value);
      }
    });
    return apiFetch(`/api/results/?${qs.toString()}`);
  },

  categories: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        qs.set(key, value);
      }
    });
    return apiFetch(`/api/categories/?${qs.toString()}`);
  },

  result: (id) => apiFetch(`/api/results/${id}/`),

  updateResult: (id, patch) =>
    apiFetch(`/api/results/${id}/`, { method: "PATCH", body: patch }),

  runBatch: (jobType, options = {}) =>
    apiFetch("/api/batch/run/", {
      method: "POST",
      body: { job_type: jobType, ...options },
    }),

  batch: (id) => apiFetch(`/api/batch/${id}/`),
};

// Cache for gid -> category ({id, name, full_path}) lookups, shared across
// pages. Alternatives in results only carry shopify gids; override dropdowns
// need the taxonomy primary key.
const gidCache = new Map();

export async function categoriesByGid(gids) {
  const missing = [...new Set(gids)].filter((g) => g && !gidCache.has(g));
  if (missing.length) {
    const data = await api.categories({ gids: missing.join(",") });
    for (const c of data.results) gidCache.set(c.shopify_gid, c);
  }
}

export function getCategory(gid) {
  return gidCache.get(gid) || null;
}