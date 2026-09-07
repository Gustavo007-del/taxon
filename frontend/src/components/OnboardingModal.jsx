import { useEffect, useState } from "react";

const LS_KEY = "sf-classifier-onboarding-seen"; // permanent ("don't show again")
const SESSION_KEY = "sf-classifier-onboarding-dismissed"; // per browser session

// First-visit welcome modal. Dismissible; "don't show again" persists in
// localStorage. A plain dismiss is remembered for the session so it doesn't
// nag on every navigation.
export default function OnboardingModal() {
  const [open, setOpen] = useState(false);
  const [dontShow, setDontShow] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(LS_KEY) || sessionStorage.getItem(SESSION_KEY)) return;
    setOpen(true);
  }, []);

  function close() {
    if (dontShow) localStorage.setItem(LS_KEY, "1");
    else sessionStorage.setItem(SESSION_KEY, "1");
    setOpen(false);
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={close}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h2 className="text-lg font-semibold mb-1">👋 Welcome to the Shopify Product Classifier</h2>
        <p className="text-sm text-gray-500 mb-4">
          This tool classifies your products into Shopify&apos;s product taxonomy — a system
          then reviews the predictions before they&apos;re used.
        </p>
        <ul className="space-y-2.5 text-sm text-gray-700 mb-5">
          <li>
            📊 <b>Dashboard</b> — see how many products are classified and start a
            classification pass (text first, images as a second check).
          </li>
          <li>
            📋 <b>Results</b> — review every prediction. Green badges = confident, amber =
            unsure, red = low confidence.
          </li>
          <li>
            ✅/❌ <b>Approve / Reject</b> — your decision is saved instantly and is never
            overwritten by later runs.
          </li>
          <li>
            ✏️ <b>Override</b> — pick a different category if the prediction looks wrong.
          </li>
        </ul>
        <label className="flex items-center gap-2 text-sm text-gray-600 mb-4 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={dontShow}
            onChange={(e) => setDontShow(e.target.checked)}
          />
          Don&apos;t show this again
        </label>
        <div className="flex justify-end">
          <button
            onClick={close}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-lg"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}