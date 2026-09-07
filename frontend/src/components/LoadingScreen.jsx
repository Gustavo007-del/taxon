export default function LoadingScreen({ label = "Loading…", hint }) {
  return (
    <div className="flex flex-col items-center justify-center py-24" role="status">
      <div className="spinner-big" />
      <p className="mt-4 text-sm font-medium text-gray-600">{label}</p>
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  );
}