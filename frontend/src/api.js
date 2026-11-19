// Petit client pour l'API FastAPI (proxifiée sur /api).
const BASE = "/api";

async function request(path, options) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Erreur ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => request("/health"),
  submitMessage: (message) => request("/leads", { method: "POST", body: JSON.stringify({ message }) }),
  reviews: (status) => request(`/reviews${status ? `?status=${status}` : ""}`),
  leads: () => request("/leads"),
  approve: (id) => request(`/reviews/${id}/approve`, { method: "POST" }),
  reject: (id) => request(`/reviews/${id}/reject`, { method: "POST" }),
};
