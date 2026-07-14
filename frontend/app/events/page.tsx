import Link from "next/link";
import { getCanonicalEvents, getHealth } from "@/lib/api";
import { severityColor, severityLabel, formatDateTime } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function EventsPage() {
  let events;
  let showcaseMode = false;
  let error: string | null = null;

  try {
    const [eventsResponse, health] = await Promise.all([
      getCanonicalEvents({ limit: 50, active: true }),
      getHealth(),
    ]);
    events = eventsResponse;
    showcaseMode = health.showcase_mode ?? false;
  } catch (e) {
    error = e instanceof Error ? e.message : "API nicht erreichbar";
    events = { items: [], total: 0, limit: 50, offset: 0 };
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Canonical Events</h1>
        <p className="mt-1 text-slate-600">
          Quellenübergreifend korrelierte Gefahrenereignisse.
        </p>
      </div>

      {showcaseMode && (
        <div className="rounded-lg border border-violet-200 bg-violet-50 p-4 text-sm text-violet-900">
          <strong>Showcase / Demo</strong> — Angezeigte Events stammen aus kuratierten
          Demoszenarien.
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {events.items.length === 0 ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
          Keine aktiven Events. Führen Sie einen Ingest aus oder aktivieren Sie{" "}
          <code className="rounded bg-slate-200 px-1">SHOWCASE_MODE=true</code>.
        </div>
      ) : (
        <div className="grid gap-3">
          {events.items.map((event) => (
            <Link
              key={event.id}
              href={`/events/${event.id}`}
              className="block rounded-lg border border-slate-200 bg-white p-4 transition-shadow hover:shadow-md"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium text-white"
                  style={{ backgroundColor: severityColor(event.severity) }}
                >
                  {severityLabel(event.severity)}
                </span>
                <span className="text-xs text-slate-400">
                  {event.member_count} Quelle(n) · {event.status}
                </span>
              </div>
              <h2 className="mt-2 font-semibold text-slate-900">{event.title}</h2>
              <p className="mt-1 text-xs text-slate-500">
                Aktualisiert: {formatDateTime(event.updated_at)}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
