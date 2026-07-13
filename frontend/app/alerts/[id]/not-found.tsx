import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-4xl font-bold text-slate-900">404</h1>
      <p className="mt-2 text-slate-600">Warnung nicht gefunden.</p>
      <Link
        href="/alerts"
        className="mt-4 inline-block text-blue-600 hover:underline"
      >
        Zur Warnungsliste
      </Link>
    </div>
  );
}
