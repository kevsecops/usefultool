import Link from "next/link";
import type { CanonicalEvent, EventSourcesResponse, ImplicationCandidate } from "@/types/events";
import type { EventAssetExposure } from "@/types/exposure";
import { severityColor, severityLabel, formatDateTime } from "@/lib/format";
import { sanitizeToPlainText } from "@/lib/sanitize";

interface EventDetailProps {
  event: CanonicalEvent;
  sources: EventSourcesResponse;
  exposures: EventAssetExposure[];
  implications: ImplicationCandidate[];
  showcaseMode?: boolean;
}

const CONFIDENCE_LABELS: Record<string, string> = {
  low: "Niedrig",
  medium: "Mittel",
  high: "Hoch",
};

const STATUS_LABELS: Record<string, string> = {
  active: "Aktiv",
  monitoring: "Beobachtung",
  ended: "Beendet",
  unknown: "Unbekannt",
};

export function EventDetail({
  event,
  sources,
  exposures,
  implications,
  showcaseMode = false,
}: EventDetailProps) {
  const limitations = [
    "Aggregierte öffentliche Daten — keine amtliche Warnung.",
    "Exposure-Analyse ist indikativ, kein wissenschaftliches Schadensmodell.",
    ...(implications.length === 0
      ? ["Keine Implikationen generiert — ggf. Exposure-Berechnung ausstehend."]
      : []),
  ];

  return (
    <div className="space-y-6">
      {showcaseMode && (
        <div className="rounded-lg border border-violet-200 bg-violet-50 p-4 text-sm text-violet-900">
          <strong>Showcase / Demo</strong> — Kuratierte Demodaten ohne externe API-Schlüssel.
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span
                className="inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium text-white"
                style={{ backgroundColor: severityColor(event.severity) }}
              >
                {severityLabel(event.severity)}
              </span>
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-700">
                {STATUS_LABELS[event.status] ?? event.status}
              </span>
              <span className="text-xs text-slate-500">
                Vertrauen: {CONFIDENCE_LABELS[event.confidence] ?? event.confidence}
              </span>
              {event.event_type && (
                <span className="text-xs text-slate-400">{event.event_type}</span>
              )}
            </div>
            <h1 className="text-2xl font-bold text-slate-900">{event.title}</h1>
            {event.correlation_reason && (
              <p className="mt-2 text-sm text-slate-600">{event.correlation_reason}</p>
            )}
          </div>
          <div className="text-right text-sm text-slate-500">
            <p className="font-medium text-slate-700">Letztes Update</p>
            <p>{formatDateTime(event.updated_at)}</p>
            <p className="mt-2 font-medium text-slate-700">Zeitraum</p>
            <p>{formatDateTime(event.started_at)}</p>
            {event.ended_at && <p>→ {formatDateTime(event.ended_at)}</p>}
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Verknüpfte Quellen" value={event.member_count} />
        <StatCard label="Alerts" value={sources.alerts.length} />
        <StatCard label="Observed Events" value={sources.observed_events.length} />
      </div>

      {sources.alerts.length > 0 || sources.observed_events.length > 0 ? (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 font-semibold text-slate-900">Verknüpfte Quellen</h2>
          {sources.alerts.length > 0 && (
            <div className="mb-4">
              <h3 className="mb-2 text-sm font-medium text-slate-700">Alerts</h3>
              <ul className="space-y-2">
                {sources.alerts.map((alert) => (
                  <li key={alert.id} className="text-sm">
                    <Link
                      href={`/alerts/${alert.id}`}
                      className="font-medium text-blue-700 hover:underline"
                    >
                      {alert.title}
                    </Link>
                    <span className="text-slate-500">
                      {" "}
                      · {alert.source} · {alert.severity}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {sources.observed_events.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium text-slate-700">Observed Events</h3>
              <ul className="space-y-2">
                {sources.observed_events.map((obs) => (
                  <li key={obs.id} className="text-sm text-slate-700">
                    <span className="font-medium">{obs.title}</span>
                    <span className="text-slate-500">
                      {" "}
                      · {obs.source} · {obs.severity}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      ) : null}

      {exposures.length > 0 && (
        <section className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
          <h2 className="mb-3 font-semibold text-emerald-900">Betroffene Assets</h2>
          <ul className="space-y-2">
            {exposures.map((exp) => (
              <li key={exp.id} className="text-sm text-emerald-900">
                <span className="font-medium">{exp.asset?.name ?? exp.asset_id}</span>
                <span className="text-emerald-700">
                  {" "}
                  ({exp.asset?.asset_type}) · {exp.exposure_type}
                  {exp.distance_km != null && ` · ${exp.distance_km.toFixed(1)} km`}
                  {exp.overlap && " · Überlappung"}
                </span>
                {exp.rationale && (
                  <p className="text-xs text-emerald-600">{exp.rationale}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {event.members.length > 0 && (
        <section className="rounded-lg border border-blue-200 bg-blue-50 p-4">
          <h2 className="mb-3 font-semibold text-blue-900">Observed Facts</h2>
          <ul className="space-y-2">
            {event.members.map((member) => (
              <li key={member.member_id} className="text-sm text-blue-900">
                <span className="font-medium">{member.title ?? member.member_id}</span>
                <span className="text-blue-600">
                  {" "}
                  · {member.member_type} · {member.source} · Verknüpfung:{" "}
                  {member.link_confidence}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {implications.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-1 font-semibold text-slate-900">
            Mögliche Implikationen (Hypothesen)
          </h2>
          <p className="mb-3 text-xs text-slate-500">
            Konservative Ableitungen — keine verifizierten Auswirkungen.
          </p>
          <ul className="space-y-3">
            {implications.map((impl) => (
              <li key={impl.id} className="text-sm text-slate-700">
                <p className="font-medium text-slate-900">{impl.title}</p>
                {impl.description && (
                  <p className="mt-1">{sanitizeToPlainText(impl.description)}</p>
                )}
                <p className="mt-1 text-xs text-slate-400">
                  {impl.category} · {impl.evidence_level} · Vertrauen: {impl.confidence}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-lg border border-slate-200 bg-slate-50 p-4">
        <h2 className="mb-2 font-semibold text-slate-700">Einschränkungen</h2>
        <ul className="list-inside list-disc space-y-1 text-sm text-slate-600">
          {limitations.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      </section>

      <div className="flex gap-3">
        <Link
          href="/map"
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
        >
          Auf Karte anzeigen
        </Link>
        <Link
          href="/events"
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Alle Events
        </Link>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}
