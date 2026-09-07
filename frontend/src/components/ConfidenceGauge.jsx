import { confidenceColor, formatPct } from "../format";

// Circular 0–100% gauge. Value stays a raw 0–1 float; rendering shows %.
export default function ConfidenceGauge({ value, size = 96 }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="text-3xl text-gray-300">—</span>;
  }
  const pct = Math.min(100, Math.max(0, Math.round(value * 100)));
  const color =
    confidenceColor(value) === "green"
      ? "#22c55e"
      : confidenceColor(value) === "amber"
      ? "#f59e0b"
      : "#ef4444";
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = (pct / 100) * c;
  return (
    <div className="relative inline-flex items-center justify-center" title={`${formatPct(value)} confident`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c - dash}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
      </svg>
      <span className="absolute text-xl font-semibold text-gray-800">{pct}%</span>
    </div>
  );
}