// Display-only helpers. The API keeps raw 0–1 floats; the UI shows 0–100%.

export function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

// Same thresholds as the classic UI, just relabeled as percentages:
// ≥75% green, 50–74% amber, <50% red.
export function confidenceColor(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  if (value >= 0.75) return "green";
  if (value >= 0.5) return "amber";
  return "red";
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

export function jobTypeLabel(type) {
  return type === "image" ? "Image pass" : "Text pass";
}