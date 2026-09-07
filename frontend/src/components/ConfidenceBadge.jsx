import { confidenceColor, formatPct } from "../format";

// Displays a 0–1 confidence as 0–100% with the classic color thresholds:
// ≥75% green, 50–74% amber, <50% red.
export default function ConfidenceBadge({ value, sub }) {
  const color = confidenceColor(value);
  if (!color) return <span className="text-gray-400">—</span>;
  const classes = {
    green: "bg-green-100 text-green-700",
    amber: "bg-amber-100 text-amber-700",
    red: "bg-red-100 text-red-700",
  }[color];
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${classes}`}
    >
      {formatPct(value)}
      {sub && <span className="font-normal opacity-70">{sub}</span>}
    </span>
  );
}