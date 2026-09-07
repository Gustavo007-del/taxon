export function Skeleton({ className }) {
  return <div className={`skeleton ${className || ""}`} />;
}

// Placeholder row used while the results list is loading.
export function TableSkeleton({ rows = 8, cols = 5 }) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      <table className="w-full text-sm">
        <tbody>
          {Array.from({ length: rows }).map((_, i) => (
            <tr key={i} className="border-t border-gray-100">
              {Array.from({ length: cols }).map((__, j) => (
                <td key={j} className="px-3 py-3">
                  <Skeleton className="h-4 w-24" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Placeholder stat cards while the dashboard is loading.
export function StatSkeleton() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <Skeleton className="h-7 w-16 mb-2" />
          <Skeleton className="h-3 w-24" />
        </div>
      ))}
    </div>
  );
}