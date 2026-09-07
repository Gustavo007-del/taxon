import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, categoriesByGid, getCategory } from "../api";
import { formatDateTime, formatPct } from "../format";
import ConfidenceBadge from "../components/ConfidenceBadge";
import ConfidenceBar from "../components/ConfidenceBar";
import ConfidenceGauge from "../components/ConfidenceGauge";
import LoadingScreen from "../components/LoadingScreen";
import StatusBadge from "../components/StatusBadge";
import Tooltip, { InfoHint } from "../components/Tooltip";
import { ArrowLeftIcon, CheckIcon, PencilIcon, XIcon } from "../components/icons";
import { notify } from "../toast";

const METHOD_HELP = {
  text_only: "Only the product's title and description were checked.",
  text_plus_image: "The product photos were checked as a second opinion.",
};

export default function ResultDetailPage() {
  const { id } = useParams();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [overrideSel, setOverrideSel] = useState("");
  const [lightbox, setLightbox] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .result(id)
      .then(async (r) => {
        const gids = (r.alternatives || []).map((a) => a.shopify_gid).filter(Boolean);
        await categoriesByGid(gids).catch(() => {});
        if (!cancelled) setResult(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Close the lightbox with Escape.
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") setLightbox(null);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function act(patch, message) {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.updateResult(id, patch);
      setResult(updated);
      notify(message || "Saved ✓");
    } catch (e) {
      setError(e.message);
      notify(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function doOverride() {
    if (!overrideSel) return;
    const cat = getCategory(overrideSel);
    if (!cat) return;
    act({ status: "approved", predicted_category_id: cat.id }, "Category updated & approved ✓");
    setOverrideSel("");
  }

  if (loading) {
    return <LoadingScreen label="Loading product…" hint="Fetching prediction and images" />;
  }

  if (error || !result) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-10 text-center">
        <div className="text-gray-700 font-medium mb-2">Couldn't load this result</div>
        <div className="text-sm text-gray-400 mb-4">{error || "Not found."}</div>
        <Link to="/results" className="text-sm text-blue-700 hover:text-blue-900">
          ← Back to results
        </Link>
      </div>
    );
  }

  const p = result.product;
  const alternatives = (result.alternatives || [])
    .map((a) => ({ ...a, category: getCategory(a.shopify_gid) }))
    .filter((a) => !result.predicted_category || a.shopify_gid !== result.predicted_category.shopify_gid);

  const infoRows = [
    ["Description", p.description],
    ["Bullets", p.bullets],
    ["Collection", p.collection_name],
    ["Color", p.product_color],
    ["Color collection", p.color_collection],
    ["Materials", p.materials],
    ["Product type", p.product_type],
    ["Raw category", p.category_raw],
    ["Raw sub-category", p.sub_category_raw],
    ["Price", p.price ? `$${p.price}` : null],
  ].filter(([, v]) => v);

  return (
    <div>
      {/* Breadcrumbs */}
      <nav className="text-xs text-gray-400 mb-2 flex items-center gap-1.5">
        <Link to="/" className="hover:text-gray-600">
          Dashboard
        </Link>
        <span>/</span>
        <Link to="/results" className="hover:text-gray-600">
          Results
        </Link>
        <span>/</span>
        <span className="text-gray-600 font-medium">{p.product_number}</span>
      </nav>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Link
          to="/results"
          className="text-sm text-blue-700 hover:text-blue-900 inline-flex items-center gap-1"
        >
          <ArrowLeftIcon className="text-xs" /> Results
        </Link>
        <h1 className="text-xl font-semibold">{p.product_number}</h1>
        <StatusBadge status={result.status} />
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* --- Product info --- */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
            <h2 className="font-medium text-gray-800 mb-1">{p.title}</h2>
            {p.brand && <p className="text-sm text-gray-500 mb-3">{p.brand}</p>}
            {infoRows.length > 0 ? (
              <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
                {infoRows.map(([label, value]) => (
                  <div key={label} className={label === "Description" || label === "Bullets" ? "col-span-2" : ""}>
                    <dt className="text-gray-500">{label}</dt>
                    <dd className="text-gray-700">{value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-sm text-gray-400">No extra product details in the spreadsheet.</p>
            )}
          </div>

          {p.image_urls && p.image_urls.length > 0 && (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
              <h2 className="font-medium text-gray-800 mb-3">
                Images{" "}
                <span className="text-xs text-gray-400 font-normal">
                  ({p.image_urls.length}) — click to enlarge
                </span>
              </h2>
              <div className="grid grid-cols-4 sm:grid-cols-5 lg:grid-cols-6 gap-2">
                {p.image_urls.map((url, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setLightbox(url)}
                    className="aspect-square overflow-hidden rounded-lg border border-gray-200 hover:ring-2 hover:ring-blue-400 transition-all group"
                    aria-label={`View product image ${i + 1}`}
                  >
                    <img
                      src={url}
                      alt={`Product image ${i + 1}`}
                      loading="lazy"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                    />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* --- Classification panel --- */}
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
            <h2 className="font-medium text-gray-800 mb-3">
              Prediction{" "}
              <InfoHint text="The system's best guess for the Shopify category, with its confidence." />
            </h2>

            <div className="flex items-center gap-4 mb-4">
              <ConfidenceGauge value={result.final_confidence} />
              <div className="text-sm flex-1">
                <div className="text-gray-500">Predicted category</div>
                <div className="font-medium leading-snug">
                  {result.predicted_category ? (
                    result.predicted_category.full_path
                  ) : (
                    <span className="text-gray-400">No prediction</span>
                  )}
                </div>
                <div className="text-xs text-gray-400 mt-1">
                  Final confidence — combines text{result.image_confidence != null ? " + image" : ""} checks
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm mb-4">
              <div className="rounded border border-gray-200 p-2 text-center">
                <ConfidenceBadge value={result.text_confidence} />
                <ConfidenceBar value={result.text_confidence} className="mt-1.5" />
                <div className="text-xs text-gray-500 mt-1">
                  Text pass <InfoHint text="Confidence from the product's title & description alone." />
                </div>
              </div>
              <div className="rounded border border-gray-200 p-2 text-center">
                <ConfidenceBadge value={result.image_confidence} />
                <ConfidenceBar value={result.image_confidence} className="mt-1.5" />
                <div className="text-xs text-gray-500 mt-1">
                  Image pass{" "}
                  <InfoHint text="Confidence from the product photos, when they were checked." />
                </div>
              </div>
            </div>

            <div className="text-xs text-gray-500 mb-4 -mt-2">
              <Tooltip text="Whether the image was also checked.">
                <span>
                  Method:{" "}
                  {result.method_used
                    ? METHOD_HELP[result.method_used] || result.method_used
                    : "—"}
                </span>
              </Tooltip>
            </div>

            {alternatives.length > 0 && (
              <div className="text-sm mb-4">
                <div className="text-gray-500 mb-1">
                  Alternatives{" "}
                  <InfoHint text="Other possible categories the system considered (close runners-up)." />
                </div>
                {alternatives.map((a) => (
                  <div key={a.shopify_gid || a.name} className="flex justify-between text-xs py-0.5">
                    <span>{a.category?.name || a.name}</span>
                    <span className="text-gray-400">{formatPct(a.score)}</span>
                  </div>
                ))}
              </div>
            )}

            {result.detected_attributes && result.detected_attributes.length > 0 && (
              <div className="text-sm">
                <div className="text-gray-500 mb-1">
                  Detected attributes & values{" "}
                  <InfoHint text="Taxonomy attributes and values found in the product's description." />
                </div>
                {result.detected_attributes.map((a) => (
                  <div key={a.handle || a.name} className="text-xs py-0.5">
                    <span className="font-medium">{a.name}:</span>{" "}
                    {a.values && a.values.length ? (
                      <span className="text-green-700">{a.values.join(", ")}</span>
                    ) : (
                      <span className="text-gray-400">no value matched</span>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div className="text-xs text-gray-400 mt-4">
              Classified {formatDateTime(result.updated_at)}
            </div>
          </div>

          {/* --- Review decision --- */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
            <h2 className="font-medium text-gray-800 mb-3">
              Review decision{" "}
              <InfoHint text="Your choice is saved instantly and is never overwritten by later classification runs." />
            </h2>

            <div className="flex gap-2 mb-4">
              <Tooltip text="Accept the prediction. Marks this product as reviewed.">
                <button
                  onClick={() => act({ status: "approved" }, "Approved ✓")}
                  disabled={busy || result.status === "approved"}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 bg-green-600 hover:bg-green-700 disabled:opacity-40 text-white text-sm font-medium px-3 py-2 rounded-lg"
                >
                  {busy ? <span className="spinner" /> : <CheckIcon />} Approve
                </button>
              </Tooltip>
              <Tooltip text="Reject the prediction. Marks this product as wrong.">
                <button
                  onClick={() => act({ status: "rejected" }, "Rejected ✗")}
                  disabled={busy || result.status === "rejected"}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white text-sm font-medium px-3 py-2 rounded-lg"
                >
                  {busy ? <span className="spinner" /> : <XIcon />} Reject
                </button>
              </Tooltip>
            </div>

            <label className="text-xs text-gray-500 block mb-1" htmlFor="override-select">
              Override category
            </label>
            <div className="flex gap-2">
              <select
                id="override-select"
                value={overrideSel}
                onChange={(e) => setOverrideSel(e.target.value)}
                className="flex-1 border border-gray-300 rounded px-2 py-1.5 text-sm bg-white"
              >
                <option value="">— choose an alternative —</option>
                {alternatives.map((a) => (
                  <option key={a.shopify_gid || a.name} value={a.shopify_gid}>
                    {a.category?.name || a.name} ({formatPct(a.score)})
                  </option>
                ))}
              </select>
              <button
                onClick={doOverride}
                disabled={busy || !overrideSel}
                className="inline-flex items-center gap-1 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-white text-sm font-medium px-3 py-1.5 rounded-lg"
              >
                <PencilIcon className="text-xs" /> Save
              </button>
            </div>
            <p className="text-xs text-gray-400 mt-3">
              Choosing a category counts as your review decision and marks the row approved.
            </p>
          </div>
        </div>
      </div>

      {/* Image lightbox */}
      {lightbox && (
        <div className="lightbox-backdrop" onClick={() => setLightbox(null)}>
          <img src={lightbox} alt="Product image enlarged" />
        </div>
      )}
    </div>
  );
}