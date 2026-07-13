"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-6">
      <h2 className="text-lg font-semibold text-red-900">
        Dashboard konnte nicht geladen werden
      </h2>
      <p className="mt-2 text-sm text-red-800">
        {error.message || "Ein unerwarteter Fehler ist aufgetreten."}
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-4 rounded-md bg-red-700 px-4 py-2 text-sm font-medium text-white hover:bg-red-800"
      >
        Erneut versuchen
      </button>
    </div>
  );
}
