const STYLES = {
  pending: "bg-gray-100 text-gray-600",
  auto_approved: "bg-green-100 text-green-700",
  approved: "bg-green-100 text-green-700",
  needs_review: "bg-amber-100 text-amber-700",
  rejected: "bg-red-100 text-red-700",
  failed: "bg-purple-100 text-purple-700",
};

const LABELS = {
  pending: "Pending",
  auto_approved: "Auto-approved",
  approved: "Approved",
  needs_review: "Needs review",
  rejected: "Rejected",
  failed: "Failed",
};

export default function StatusBadge({ status }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
        STYLES[status] || STYLES.pending
      }`}
    >
      {LABELS[status] || status}
    </span>
  );
}