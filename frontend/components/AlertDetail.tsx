import Link from "next/link";
import type { Alert } from "@/types/alert";
import {
  categoryLabel,
  formatDateTime,
  severityColor,
  severityLabel,
  sourceLabel,
  ingestModeLabel,
} from "@/lib/format";
import { sanitizeToPlainText } from "@/lib/sanitize";
import { AlertMiniMap } from "@/components/AlertMiniMap";

interface AlertDetailProps {
  alert: Alert;
}

export function AlertDetail({ alert }: AlertDetailProps) {
  const description = sanitizeToPlainText(alert.description);
  const instruction = sanitizeToPlainText(alert.instruction);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span
              className="inline-flex rounded-full px-3 py-1 text-sm font-medium text-white"
              style={{ backgroundColor: severityColor(alert.severity) }}
            >
              {severityLabel(alert.severity)}
            </span>
            <span className="text-sm text-slate-500">
              {sourceLabel(alert.source)}
            </span>
            <span
              className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                alert.ingest_mode === "fixture"
                  ? "bg-amber-100 text-amber-800"
                  : "bg-emerald-100 text-emerald-800"
              }`}
            >
              {ingestModeLabel(alert.ingest_mode)}
            </span>
            {alert.country_code && (
              <span className="text-sm text-slate-500">
                {alert.country_name ?? alert.country_code}
              </span>
            )}
          </div>
          <h1 className="text-2xl font-bold text-slate-900">{alert.title}</h1>
          {alert.event_type && (
            <p className="mt-1 text-sm text-slate-500">{alert.event_type}</p>
          )}
        </div>
        {alert.source_url && (
          <a
            href={alert.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            Originalquelle öffnen
          </a>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {description && (
            <section className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-2 font-semibold text-slate-900">Beschreibung</h2>
              <p className="whitespace-pre-wrap text-sm text-slate-700">
                {description}
              </p>
            </section>
          )}

          {instruction && (
            <section className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-2 font-semibold text-slate-900">
                Handlungsempfehlung
              </h2>
              <p className="whitespace-pre-wrap text-sm text-slate-700">
                {instruction}
              </p>
            </section>
          )}

          <section className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 font-semibold text-slate-900">Details</h2>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-slate-500">Kategorie</dt>
              <dd className="text-slate-900">{categoryLabel(alert.category)}</dd>
              <dt className="text-slate-500">Status</dt>
              <dd className="text-slate-900">
                {alert.is_active ? "Aktiv" : "Inaktiv"} ({alert.status})
              </dd>
              <dt className="text-slate-500">Ausgestellt</dt>
              <dd className="text-slate-900">{formatDateTime(alert.issued_at)}</dd>
              <dt className="text-slate-500">Gültig ab</dt>
              <dd className="text-slate-900">
                {formatDateTime(alert.starts_at ?? alert.effective_at)}
              </dd>
              <dt className="text-slate-500">Ablauf</dt>
              <dd className="text-slate-900">{formatDateTime(alert.expires_at)}</dd>
              <dt className="text-slate-500">Region</dt>
              <dd className="text-slate-900">
                {alert.region ?? alert.location_name ?? "—"}
              </dd>
              <dt className="text-slate-500">Quellen-ID</dt>
              <dd className="font-mono text-xs text-slate-700">
                {alert.source_alert_id}
              </dd>
              <dt className="text-slate-500">Erfasst</dt>
              <dd className="text-slate-900">{formatDateTime(alert.ingested_at)}</dd>
              <dt className="text-slate-500">Zuletzt gesehen</dt>
              <dd className="text-slate-900">
                {formatDateTime(alert.last_seen_at)}
              </dd>
            </dl>
          </section>
        </div>

        <div className="space-y-4">
          <AlertMiniMap alert={alert} />
          <Link
            href="/alerts"
            className="block text-center text-sm text-blue-600 hover:underline"
          >
            ← Zurück zur Liste
          </Link>
        </div>
      </div>
    </div>
  );
}
