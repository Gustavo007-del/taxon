import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { formatDateTime, formatPct, jobTypeLabel } from "../format";
import {
  AlertIcon,
  BarChartIcon,
  CheckCircleIcon,
  ClockIcon,
  PackageIcon,
  PlayIcon,
  XCircleIcon,
} from "../components/icons";
import LoadingScreen from "../components/LoadingScreen";
import Tooltip from "../components/Tooltip";

const STAT_HELP = {
  products: "Total products imported from the supplier spreadsheet.",
  pending: "Products that haven't been classified yet.",
  autoApproved: "Classified automatically with high confidence — no human needed.",
  needsReview: "Low confidence or text/image disagreement — a human should look.",
  approved: "Manually approved by a reviewer.",
  rejected: "Marked as wrong by a reviewer.",
  failed: "Classification failed; they are retried on the next run.",
  avg: "Average confidence across all classified products.",
};

export default function DashboardPage() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [runningType, setRunningType] = useState(null); // "text" | "image" | null
  const [job, setJob] = useState(null); // latest running/just-finished job
  const [limit, setLimit] = useState("");
  const timerRef = useRef(null);

  const loadStats = useCallback(async () => {
    try {
      setStats(await api.stats());
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    loadStats();
    return () => clearInterval(timerRef.current);
  }, [loadStats]);

  function stopPolling() {
    clearInterval(timerRef.current);
    timerRef.current = null;
  }

  function poll(jobId) {
    stopPolling();
    timerRef.current = setInterval(async () => {
      try {
        const data = await api.batch(jobId);
        setJob(data);
        if (data.status === "completed" || data.status === "failed") {
          stopPolling();
          setRunningType(null);
          loadStats(); // refresh counts once the pass finishes
          setTimeout(() => setJob(null), 6000);
        }
      } catch {
        // keep polling; the runner may briefly be unavailable
      }
    }, 2000);
  }

  async function runPass(jobType) {
    setError(null);
    setRunningType(jobType);
    try {
      const started = await api.runBatch(
        jobType,
        limit && Number(limit) > 0 ? { limit: Number(limit) } : {}
      );
      setJob({ ...started, total: 0, processed: 0, failed: 0 });
      poll(started.id);
    } catch (e) {
      setError(e.message);
      setRunningType(null);
    }
  }

  const byStatus = stats?.by_status || {};
  const resultsTotal = stats?.results_total || 0;
  const jobPct = job?.total ? Math.min(100, Math.round((100 * job.processed) / job.total)) : 0;
  const needsReview = byStatus.needs_review || 0;

  // Card config: label, value, icon, colors, link, share-of-total bar.
  const cards = [
    {
      key: "products",
      label: "Products imported",
      value: stats?.products_total,
      icon: PackageIcon,
      chip: "bg-blue-100 text-blue-600",
      bar: 1,
      link: "/results",
      help: STAT_HELP.products,
    },
    {
      key: "pending",
      label: "Pending (not classified)",
      value: stats?.pending,
      icon: ClockIcon,
      chip: "bg-gray-100 text-gray-500",
      bar: resultsTotal ? 1 - resultsTotal / (stats?.products_total || 1) : 0,
      link: "/results?status=pending",
      help: STAT_HELP.pending,
    },
    {
      key: "auto",
      label: "Auto-approved",
      value: byStatus.auto_approved,
      icon: CheckCircleIcon,
      chip: "bg-green-100 text-green-600",
      bar: stats?.products_total ? byStatus.auto_approved / stats.products_total : 0,
      link: "/results?status=auto_approved",
      help: STAT_HELP.autoApproved,
    },
    {
      key: "review",
      label: "Needs review",
      value: needsReview,
      icon: AlertIcon,
      chip: "bg-amber-100 text-amber-600",
      bar: stats?.products_total ? needsReview / stats.products_total : 0,
      link: "/results?status=needs_review",
      help: STAT_HELP.needsReview,
    },
    {
      key: "approved",
      label: "Approved (manual)",
      value: byStatus.approved,
      icon: CheckCircleIcon,
      chip: "bg-green-100 text-green-500",
      bar: stats?.products_total ? byStatus.approved / stats.products_total : 0,
      link: "/results?status=approved",
      help: STAT_HELP.approved,
    },
    {
      key: "rejected",
      label: "Rejected",
      value: byStatus.rejected,
      icon: XCircleIcon,
      chip: "bg-red-100 text-red-500",
      bar: stats?.products_total ? byStatus.rejected / stats.products_total : 0,
      link: "/results?status=rejected",
      help: STAT_HELP.rejected,
    },
    {
      key: "failed",
      label: "Failed",
      value: byStatus.failed,
      icon: AlertIcon,
      chip: "bg-purple-100 text-purple-500",
      bar: stats?.products_total ? byStatus.failed / stats.products_total : 0,
      link: "/results?status=failed",
      help: STAT_HELP.failed,
    },
    {
      key: "avg",
      label: "Avg confidence",
      value:
        stats?.avg_confidence !== null && stats?.avg_confidence !== undefined
          ? formatPct(stats.avg_confidence)
          : "—",
      icon: BarChartIcon,
      chip: "bg-indigo-100 text-indigo-500",
      bar: stats?.avg_confidence ?? 0,
      link: null,
      help: STAT_HELP.avg,
    },
  ];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-xl font-semibold">Dashboard</h1>
          <p className="text-sm text-gray-500">
            Overview of classification progress. Start a pass when new products arrive.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600" htmlFor="batch-limit">
            Limit
          </label>
          <input
            id="batch-limit"
            type="number"
            min="0"
            placeholder="all"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1.5 text-sm w-24"
          />
          <Tooltip text="Run the text pass: classify products by title & description. Runs on products not yet classified (or failed).">
            <button
              onClick={() => runPass("text")}
              disabled={runningType !== null}
              className="inline-flex items-center gap-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium px-3 py-1.5 rounded-lg"
            >
              {runningType === "text" ? (
                <span className="spinner" />
              ) : (
                <PlayIcon className="text-sm" />
              )}
              {runningType === "text" ? "Classifying…" : "Run text pass"}
            </button>
          </Tooltip>
          <Tooltip text="Run the image pass: check product photos as a second opinion on rows that need review.">
            <button
              onClick={() => runPass("image")}
              disabled={runningType !== null}
              className="inline-flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium px-3 py-1.5 rounded-lg"
            >
              {runningType === "image" ? (
                <span className="spinner" />
              ) : (
                <PlayIcon className="text-sm" />
              )}
              {runningType === "image" ? "Classifying…" : "Run image pass"}
            </button>
          </Tooltip>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      {/* Review queue banner */}
      {stats && needsReview > 0 && (
        <Link
          to="/results?status=needs_review"
          className="mb-6 flex flex-wrap items-center gap-3 bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-xl px-4 py-3 hover:shadow-sm transition-shadow"
        >
          <span className="text-2xl">🔍</span>
          <span className="text-sm font-medium text-amber-900">
            {needsReview} product{needsReview === 1 ? "" : "s"} need{needsReview === 1 ? "s" : ""} a
            human review
          </span>
          <span className="text-sm text-amber-700">(low confidence or text/image disagreement)</span>
          <span className="ml-auto text-sm font-medium text-amber-800 bg-white border border-amber-300 rounded-lg px-3 py-1.5">
            Open review queue →
          </span>
        </Link>
      )}

      {/* Live batch progress */}
      {job && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
          <div className="flex justify-between text-sm mb-2">
            <span className="font-medium">
              {jobTypeLabel(job.job_type)} <span className="text-gray-400">#{job.id}</span>
            </span>
            <span className="text-gray-500">
              {job.status === "completed"
                ? "Completed ✓"
                : job.status === "failed"
                ? "Failed ✗"
                : "Running…"}
            </span>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex-1 bg-gray-200 rounded h-2.5 overflow-hidden">
              <div
                className={`h-2.5 rounded transition-all ${
                  job.status === "failed"
                    ? "bg-red-500"
                    : job.status === "completed"
                    ? "bg-green-500"
                    : "bg-blue-500 animate-pulse"
                }`}
                style={{ width: `${jobPct}%` }}
              />
            </div>
            <span className="text-xs text-gray-500 whitespace-nowrap">
              {job.processed}/{job.total}
              {job.failed ? ` (${job.failed} failed)` : ""}
            </span>
          </div>
        </div>
      )}

      {!stats ? (
        <LoadingScreen label="Loading dashboard…" hint="Fetching classification stats" />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {cards.map((card) => {
            const Icon = card.icon;
            return (
              <Tooltip key={card.key} text={card.help}>
                <div className="w-full">
                  {card.link ? (
                    <Link
                      to={card.link}
                      className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 h-full min-h-[160px] flex flex-col justify-center hover:shadow-md hover:-translate-y-0.5 transition-all"
                    >
                      <div className="flex items-center justify-between">
                        <span className={`inline-flex items-center justify-center w-9 h-9 rounded-lg ${card.chip}`}>
                          <Icon className="text-lg" />
                        </span>
                        <span className="text-2xl font-semibold">{card.value}</span>
                      </div>
                      <div className="text-sm text-gray-500 mt-2">{card.label}</div>
                      <div className="mt-auto">
                        <div className="h-1.5 bg-gray-100 rounded overflow-hidden">
                          <div
                            className={`h-1.5 rounded transition-all ${
                              card.link ? "bg-blue-400" : "bg-indigo-400"
                            }`}
                            style={{ width: `${Math.round(card.bar * 100)}%` }}
                          />
                        </div>
                      </div>
                    </Link>
                  ) : (
                    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 h-full min-h-[160px] flex flex-col justify-center">
                      <div className="flex items-center justify-between">
                        <span className={`inline-flex items-center justify-center w-9 h-9 rounded-lg ${card.chip}`}>
                          <Icon className="text-lg" />
                        </span>
                        <span className="text-2xl font-semibold">{card.value}</span>
                      </div>
                      <div className="text-sm text-gray-500 mt-2">{card.label}</div>
                      <div className="mt-auto">
                        <div className="h-1.5 bg-gray-100 rounded overflow-hidden">
                          <div
                            className="h-1.5 rounded bg-indigo-400"
                            style={{ width: `${Math.round(card.bar * 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </Tooltip>
            );
          })}
        </div>
      )}

      {/* Recent batch jobs */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 font-medium text-sm">
          Recent batch jobs
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-gray-500 text-xs uppercase">
            <tr>
              <th className="px-4 py-2">Job</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2 w-1/3">Progress</th>
              <th className="px-4 py-2">Result</th>
              <th className="px-4 py-2">Started</th>
            </tr>
          </thead>
          <tbody>
            {(stats?.recent_jobs || []).map((j) => {
              const pct = j.total ? Math.min(100, Math.round((100 * j.processed) / j.total)) : 0;
              return (
                <tr key={j.id} className="border-t border-gray-100">
                  <td className="px-4 py-2">{jobTypeLabel(j.job_type)}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                        j.status === "completed"
                          ? "bg-green-100 text-green-700"
                          : j.status === "failed"
                          ? "bg-red-100 text-red-700"
                          : "bg-blue-100 text-blue-700"
                      }`}
                    >
                      {j.status}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-gray-200 rounded h-2 overflow-hidden">
                        <div
                          className={`h-2 rounded ${
                            j.status === "failed" ? "bg-red-500" : "bg-blue-500"
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500 whitespace-nowrap">
                        {j.processed}/{j.total}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-500">
                    {j.failed ? `${j.failed} failed` : "—"}
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-500">{formatDateTime(j.started_at)}</td>
                </tr>
              );
            })}
            {(stats?.recent_jobs || []).length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  No batch jobs yet — run a classification pass above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}