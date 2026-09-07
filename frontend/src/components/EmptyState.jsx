export default function EmptyState({ icon = "🎉", title, hint }) {
  return (
    <div className="text-center py-12">
      <div className="text-4xl mb-2">{icon}</div>
      <div className="font-medium text-gray-700">{title}</div>
      {hint && <div className="text-sm text-gray-400 mt-1">{hint}</div>}
    </div>
  );
}