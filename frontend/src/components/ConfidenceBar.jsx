import { confidenceColor } from "../format";

export default function ConfidenceBar({ value, className = "" }) {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  const pct = Math.min(100, Math.max(0, Math.round(value * 100)));
  const color =
    confidenceColor(value) === "green"
      ? "bg-green-500"
      : confidenceColor(value) === "amber"
      ? "bg-amber-500"
      : "bg-red-500";
  return (
    <div className={`h-1.5 bg-gray-200 rounded overflow-hidden ${className}`}>
      <div
        className={`h-1.5 ${color} rounded transition-all`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}