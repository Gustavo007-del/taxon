import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, categoriesByGid, getCategory } from "../api";
import { formatPct } from "../format";
import ConfidenceBadge from "../components/ConfidenceBadge";
import ConfidenceBar from "../components/ConfidenceBar";
import EmptyState from "../components/EmptyState";
import LoadingScreen from "../components/LoadingScreen";
import StatusBadge from "../components/StatusBadge";
import { TableSkeleton } from "../components/Skeleton";
import Tooltip, { InfoHint } from "../components/Tooltip";
import { CheckIcon, PencilIcon, SearchIcon, XIcon } from "../components/icons";
import { notify } from "../toast";

const PAGE_SIZE = 25;

const METHOD_LABELS = {
  text_only: "Text only",
  text_plus_image: "Text + image",
};

const HEADER_HELP = {
  product: "Product number, title and brand from the supplier spreadsheet.",
  category:
    "Predicted Shopify category. Below it: other categories the system considered (alternatives).",
  confidence: "How sure the system is about this category (0–100%).",
  method: "Whether the image was also checked: 'Text only' or 'Text + image'.",
  status: "Auto-approved / needs a human look / manually approved.",
  attributes: "Taxonomy attributes and values found in the product's description.",
  actions: "Approve, reject or override the prediction for this product.",
};

export default function ResultsListPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const status = searchParams.get("status") || "";
  const q = searchParams.get("q") || "";
  const rawMin = searchParams.get("min_confidence");
  const minConf = rawMin ? parseFloat(rawMin) : null; // 0–1
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10) || 1);
  const sliderVal = minConf !== null && !Number.isNaN(minConf) ? Math.round(minConf * 100) : 0;

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [overrideSel, setOverrideSel] = useState({}); // resultId -> shopify_gid

  function setFilters(patch) {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([k, v]) => {
      if (v === "" || v === null || v === undefined) next.delete(k);
      else next.set(k, String(v));
    });
    if (!("page" in patch)) next.delete("page");
    setSearchParams(next);
  }

  // Press "/" anywhere to focus the search box (unless typing in a field).
  useEffect(() => {
    function onKey(e) {
      if (e.key !== "/") return;
      const tag = document.activeElement?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      e.preventDefault();
      document.querySelector('input[placeholder*="Search"]')?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .results({
        status: status || undefined,
        min_confidence: minConf !== null ? minConf : undefined,
        q: q || undefined,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      })
      .then(async (result) => {
        // Warm the gid -> category cache so override dropdowns can resolve pks.
        const gids = [];
        for (const r of result.results) {
          for (const a of r.alternatives || []) if (a.shopify_gid) gids.push(a.shopify_gid);
        }
        await categoriesByGid(gids).catch(() => {});
        if (!cancelled) setData(result);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e.message);
          setData(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status, minConf, q, page]);

  function matchesFilter(r) {
    if (status && r.status !== status) return false;
    if (minConf !== null && (r.final_confidence ?? 0) < minConf) return false;
    return true;
  }

  // Apply a PATCH response: update the row in place, or drop it if it no
  // longer matches the active filter.
  function applyPatch(updated) {
    setData((d) => {
      if (!d) return d;
      const keep = matchesFilter(updated);
      return {
        ...d,
        count: d.count - (keep ? 0 : 1),
        results: keep
          ? d.results.map((r) => (r.id === updated.id ? updated : r))
          : d.results.filter((r) => r.id !== updated.id),
      };
    });
  }

  async function act(resultId, patch, message) {
    setBusyId(resultId);
    setError(null);
    try {
      const updated = await api.updateResult(resultId, patch);
      applyPatch(updated);
      notify(message || "Saved ✓");
    } catch (e) {
      setError(e.message);
      notify(e.message, "error");
    } finally {
      setBusyId(null);
    }
  }

  function override(resultId) {
    const gid = overrideSel[resultId];
    if (!gid) return;
    const cat = getCategory(gid);
    if (!cat) return;
    act(resultId, { status: "approved", predicted_category_id: cat.id }, "Category updated & approved ✓");
  }

  const pages = Math.max(1, Math.ceil((data?.count || 0) / PAGE_SIZE));

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Classification Results</h1>
        <span className="text-sm text-gray-500">{data ? `${data.count} result(s)` : "…"}</span>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3 mb-4 bg-white rounded-lg shadow-sm border border-gray-200 p-3">
        <select
          value={status}
          onChange={(e) => setFilters({ status: e.target.value })}
          className="border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          <option value="needs_review">Needs review</option>
          <option value="auto_approved">Auto-approved</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="failed">Failed</option>
          <option value="pending">Pending</option>
        </select>

        <Tooltip text="Only show results with at least this confidence.">
          <label className="flex items-center gap-2 text-sm text-gray-600">
            Min confidence
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={sliderVal}
              onChange={(e) => {
                const v = Number(e.target.value);
                setFilters(v === 0 ? { min_confidence: "" } : { min_confidence: (v / 100).toFixed(2) });
              }}
              className="w-32"
            />
            <span className="text-xs text-gray-500 w-9">{sliderVal}%</span>
          </label>
        </Tooltip>

        <div className="relative">
          <SearchIcon className="absolute left-2.5 top-2 text-gray-400 text-sm" />
          <input
            type="text"
            placeholder="Search product # / title"
            value={q}
            onChange={(e) => setFilters({ q: e.target.value })}
            className="border border-gray-300 rounded pl-8 pr-2 py-1.5 text-sm w-56"
          />
        </div>

        {(status || minConf !== null || q) && (
          <button
            onClick={() => setFilters({ status: "", min_confidence: "", q: "" })}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Clear
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      {loading ? (
        data ? (
          <TableSkeleton rows={10} cols={6} />
        ) : (
          <LoadingScreen label="Loading results…" hint="Fetching classification results" />
        )
      ) : !data || data.results.length === 0 ? (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <EmptyState
            icon={status === "needs_review" ? "🎉" : "🔍"}
            title={
              status === "needs_review"
                ? "No products need review right now"
                : "No results match your filters"
            }
            hint={
              status === "needs_review"
                ? "Everything classified so far is confident or already approved. Check back after the next run."
                : "Try clearing the status filter or lowering the confidence threshold."
            }
          />
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-x-auto sticky-head">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-3 py-2">
                  <span className="inline-flex items-center gap-1">
                    Product <InfoHint text={HEADER_HELP.product} />
                  </span>
                </th>
                <th className="px-3 py-2">
                  <span className="inline-flex items-center gap-1">
                    Predicted category <InfoHint text={HEADER_HELP.category} />
                  </span>
                </th>
                <th className="px-3 py-2">
                  <span className="inline-flex items-center gap-1">
                    Confidence <InfoHint text={HEADER_HELP.confidence} />
                  </span>
                </th>
                <th className="px-3 py-2">
                  <span className="inline-flex items-center gap-1">
                    Method <InfoHint text={HEADER_HELP.method} />
                  </span>
                </th>
                <th className="px-3 py-2">
                  <span className="inline-flex items-center gap-1">
                    Status <InfoHint text={HEADER_HELP.status} />
                  </span>
                </th>
                <th className="px-3 py-2">
                  <span className="inline-flex items-center gap-1">
                    Attributes <InfoHint text={HEADER_HELP.attributes} />
                  </span>
                </th>
                <th className="px-3 py-2">
                  <span className="inline-flex items-center gap-1">
                    Actions <InfoHint text={HEADER_HELP.actions} />
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((r) => {
                const alternatives = (r.alternatives || [])
                  .map((a) => ({ ...a, category: getCategory(a.shopify_gid) }))
                  .filter((a) => !r.predicted_category || a.shopify_gid !== r.predicted_category.shopify_gid);
                const busy = busyId === r.id;
                return (
                  <tr key={r.id} className="border-t border-gray-100 align-top hover-row">
                    <td className="px-3 py-2">
                      <div className="flex gap-2">
                        {r.product.image_urls?.[0] && (
                          <img
                            src={r.product.image_urls[0]}
                            alt=""
                            loading="lazy"
                            className="w-10 h-10 object-cover rounded border border-gray-200"
                            onError={(e) => {
                              e.currentTarget.style.display = "none";
                            }}
                          />
                        )}
                        <div>
                          <Link
                            to={`/results/${r.id}`}
                            className="font-medium text-blue-700 hover:text-blue-900"
                          >
                            {r.product.product_number}
                          </Link>
                          <br />
                          <span className="text-gray-700">
                            {r.product.title.length > 70
                              ? `${r.product.title.slice(0, 70)}…`
                              : r.product.title}
                          </span>
                          <br />
                          <span className="text-xs text-gray-400">{r.product.brand}</span>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      {r.predicted_category ? (
                        <Link
                          to={`/results/${r.id}`}
                          className="text-gray-800 hover:text-blue-700"
                        >
                          {r.predicted_category.full_path}
                        </Link>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                      {alternatives.length > 0 && (
                        <div className="text-xs text-gray-400">
                          <Tooltip
                            text="Other possible categories the system considered (alternatives)."
                            className="w-full"
                          >
                            <span className="truncate block max-w-[260px]">
                              {alternatives.slice(0, 2).map((a, i) => (
                                <span key={a.shopify_gid || i}>
                                  {a.category?.name || a.name}
                                  {i === 0 && alternatives.length > 1 ? " · " : ""}
                                </span>
                              ))}
                            </span>
                          </Tooltip>
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 min-w-[120px]">
                      <ConfidenceBadge value={r.final_confidence} />
                      <ConfidenceBar value={r.final_confidence} className="mt-1.5" />
                      <div className="text-xs text-gray-400 mt-1">
                        text {r.text_confidence !== null && r.text_confidence !== undefined
                          ? formatPct(r.text_confidence)
                          : "—"}
                        {r.image_confidence !== null && r.image_confidence !== undefined && (
                          <> · img {formatPct(r.image_confidence)}</>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <Tooltip text={HEADER_HELP.method}>
                        <span>{METHOD_LABELS[r.method_used] || r.method_used || "—"}</span>
                      </Tooltip>
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-600">
                      {(r.detected_attributes || []).slice(0, 3).map((a) => (
                        <div key={a.handle || a.name}>
                          <span className="font-medium">{a.name}:</span>{" "}
                          {a.values && a.values.length ? a.values.join(", ") : "—"}
                        </div>
                      ))}
                      {(r.detected_attributes || []).length === 0 && <span className="text-gray-400">—</span>}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <div className="flex flex-col gap-1.5 items-start">
                        <Link
                          to={`/results/${r.id}`}
                          className="text-xs text-blue-700 hover:text-blue-900"
                        >
                          View detail →
                        </Link>
                        <div className="flex gap-1">
                          <Tooltip text="Approve this prediction (marks it as reviewed by a human).">
                            <button
                              onClick={() => act(r.id, { status: "approved" }, "Approved ✓")}
                              disabled={busy || r.status === "approved"}
                              className="inline-flex items-center gap-1 bg-green-600 hover:bg-green-700 disabled:opacity-40 text-white text-xs px-2 py-1 rounded"
                            >
                              {busy ? <span className="spinner" /> : <CheckIcon className="text-xs" />} Approve
                            </button>
                          </Tooltip>
                          <Tooltip text="Reject this prediction (marks it as wrong).">
                            <button
                              onClick={() => act(r.id, { status: "rejected" }, "Rejected ✗")}
                              disabled={busy || r.status === "rejected"}
                              className="inline-flex items-center gap-1 bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white text-xs px-2 py-1 rounded"
                            >
                              {busy ? <span className="spinner" /> : <XIcon className="text-xs" />} Reject
                            </button>
                          </Tooltip>
                        </div>
                        <Tooltip text="Pick a different category — this counts as your review decision and approves the row.">
                          <span className="inline-flex items-center gap-1">
                            <PencilIcon className="text-xs text-gray-500" />
                            <select
                              value={overrideSel[r.id] || ""}
                              onChange={(e) =>
                                setOverrideSel((s) => ({ ...s, [r.id]: e.target.value }))
                              }
                              className="border border-gray-300 rounded px-1 py-0.5 text-xs bg-white max-w-[180px]"
                              aria-label="Override category"
                            >
                              <option value="">Override…</option>
                              {alternatives.map((a) => (
                                <option key={a.shopify_gid} value={a.shopify_gid}>
                                  {a.category?.name || a.name} ({formatPct(a.score)})
                                </option>
                              ))}
                            </select>
                            <button
                              onClick={() => override(r.id)}
                              disabled={busy || !overrideSel[r.id]}
                              className="bg-gray-700 hover:bg-gray-800 disabled:opacity-40 text-white text-xs px-2 py-0.5 rounded"
                            >
                              Set
                            </button>
                          </span>
                        </Tooltip>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {data && data.results.length > 0 && (
        <div className="mt-4 text-sm flex items-center gap-3">
          {page > 1 ? (
            <button
              onClick={() => setFilters({ page: page - 1 })}
              className="text-blue-700 hover:text-blue-900"
            >
              ← prev
            </button>
          ) : (
            <span className="text-gray-300">← prev</span>
          )}
          <span className="text-gray-600">
            page {page} / {pages}
          </span>
          {page < pages ? (
            <button
              onClick={() => setFilters({ page: page + 1 })}
              className="text-blue-700 hover:text-blue-900"
            >
              next →
            </button>
          ) : (
            <span className="text-gray-300">next →</span>
          )}
        </div>
      )}
    </div>
  );
}