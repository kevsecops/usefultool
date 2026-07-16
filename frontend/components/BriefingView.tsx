import type { Briefing } from "@/types/briefing";
import type { Stats } from "@/types/stats";
import type { SourceInfo } from "@/types/source";
import { categoryLabel, formatDateTime, ingestModeBadgeClass, ingestModeLabel, sourceHealthBadgeClass, sourceHealthLabel, sourceLabel } from "@/lib/format";
import { distinctSourceCount, normalizeBriefingContent, resolveBySource } from "@/lib/briefing";
import Link from "next/link";

interface BriefingViewProps {
  briefing: Briefing | null;
  stats: Stats;
  sources?: SourceInfo[];
  demoMode?: boolean;
  showcaseMode?: boolean;
}

const CONFIDENCE_LABELS: Record<string, string> = {
  low: "Niedrig",
  medium: "Mittel",
  high: "Hoch",
};

function isBriefingStale(briefing: Briefing, stats: Stats): boolean {
  if (!stats.last_ingest) return false;
  return new Date(briefing.generated_at) < new Date(stats.last_ingest);
}

function snapshotActiveCount(content: Briefing["content"]): number {
  if (content.active_count > 0) return content.active_count;
  return content.source_alert_ids.length;
}

function snapshotRiskScore(briefing: Briefing): number {
  return briefing.content.overall_risk_score ?? briefing.overall_risk_score;
}

export function BriefingView({
  briefing,
  stats,
  sources = [],
  demoMode = false,
  showcaseMode = false,
}: BriefingViewProps) {
  if (!briefing) {
    return (
      <div className="space-y-6">
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h2 className="font-semibold text-amber-900">Kein Briefing verfügbar</h2>
          <p className="mt-1 text-sm text-amber-800">
            Es wurde noch kein Briefing generiert. Führen Sie einen Ingest mit{" "}
            <code className="rounded bg-amber-100 px-1">--generate-briefing</code>{" "}
            aus oder nutzen Sie{" "}
            <code className="rounded bg-amber-100 px-1">python -m app.jobs.cli generate-briefing</code>.
          </p>
        </div>
        <StatsFallback stats={stats} />
      </div>
    );
  }

  const content = normalizeBriefingContent(briefing.content);
  const isLlm = briefing.type === "llm";
  const stale = isBriefingStale(briefing, stats);
  const activeCount = snapshotActiveCount(content);
  const riskScore = snapshotRiskScore(briefing);
  const bySource = resolveBySource(content, stats);
  const sourceCount = distinctSourceCount(bySource);
  const sourceFetchById = new Map(sources.map((s) => [s.id, s.last_fetch]));

  return (
    <div className="space-y-6">
      {stale && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
          <h2 className="font-semibold text-amber-900">
            Briefing veraltet — bitte neu generieren
          </h2>
          <p className="mt-1 text-sm text-amber-800">
            Dieses Briefing wurde am {formatDateTime(briefing.generated_at)} erstellt,
            aber die Warnungsdaten wurden zuletzt am{" "}
            {stats.last_ingest ? formatDateTime(stats.last_ingest) : "—"} aktualisiert.
            Die angezeigten Zahlen sind ein Snapshot vom Erstellungszeitpunkt und können
            von der aktuellen Startseite abweichen.
          </p>
          <p className="mt-2 text-sm text-amber-800">
            Aktualisieren mit:{" "}
            <code className="rounded bg-amber-100 px-1">
              python -m app.jobs.cli generate-briefing
            </code>{" "}
            oder Ingest mit{" "}
            <code className="rounded bg-amber-100 px-1">--generate-briefing</code>.
            Live-Dashboard:{" "}
            <Link href="/" className="font-medium text-amber-900 underline hover:no-underline">
              Startseite
            </Link>
          </p>
        </div>
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  isLlm
                    ? "bg-violet-100 text-violet-800"
                    : "bg-slate-100 text-slate-700"
                }`}
              >
                {isLlm ? "LLM-Analyse" : "Regelbasiert"}
              </span>
              <span className="text-sm text-slate-500">
                Vertrauen:{" "}
                {CONFIDENCE_LABELS[briefing.overall_confidence] ?? briefing.overall_confidence}
              </span>
              {briefing.llm_model && (
                <span className="text-xs text-slate-400">({briefing.llm_model})</span>
              )}
            </div>
            <p className="mt-2 text-lg text-slate-800">{content.summary}</p>
          </div>
          <div className="text-right text-sm text-slate-500">
            <p className="font-medium text-slate-700">Generiert am</p>
            <p>{formatDateTime(briefing.generated_at)}</p>
            <p className="mt-2 font-medium text-slate-700">Risk Score (Snapshot)</p>
            <p className="text-lg font-semibold text-slate-900">
              {riskScore}/100
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Aktive Warnungen (Snapshot)" value={activeCount} />
        <StatCard label="Global Risk Score (Snapshot)" value={riskScore} />
        <StatCard
          label="Betroffene Regionen"
          value={content.affected_regions.length}
        />
        <StatCard label="Datenquellen" value={sourceCount} />
      </div>

      {bySource.items.length > 0 ? (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 font-semibold text-slate-900">Nach Datenquelle</h3>
          {bySource.derived && (
            <p className="mb-3 text-xs text-amber-700">
              {bySource.reason === "live_stats"
                ? "Quellenaufteilung aus Live-Statistik (Briefing-Snapshot ohne by_source — bitte Briefing neu generieren)."
                : "Quellenaufteilung aus wesentlichen Ereignissen geschätzt — bitte Briefing neu generieren für vollständige Snapshot-Daten."}
            </p>
          )}
          <ul className="space-y-2">
            {bySource.items.map((item) => (
              <li
                key={item.source}
                className="flex items-center justify-between gap-4 text-sm"
              >
                <div>
                  <span className="text-slate-700">
                    {item.label || sourceLabel(item.source as Parameters<typeof sourceLabel>[0])}
                  </span>
                  {sourceFetchById.get(item.source) && (
                    <p className="text-xs text-slate-400">
                      Letzter Abruf: {formatDateTime(sourceFetchById.get(item.source))}
                    </p>
                  )}
                  {sources.find((s) => s.id === item.source)?.ingest_mode && (
                    <span
                      className={`mt-0.5 inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-xs font-medium ${ingestModeBadgeClass(
                        sources.find((s) => s.id === item.source)?.ingest_mode,
                      )}`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          sources.find((s) => s.id === item.source)?.ingest_mode === "showcase"
                            ? "bg-violet-500"
                            : sources.find((s) => s.id === item.source)?.ingest_mode === "fixture"
                              ? "bg-amber-500"
                              : "bg-emerald-500"
                        }`}
                        aria-hidden
                      />
                      {ingestModeLabel(sources.find((s) => s.id === item.source)?.ingest_mode)}
                    </span>
                  )}
                </div>
                <span className="font-medium text-slate-900">{item.count}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : activeCount > 0 ? (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h3 className="mb-2 font-semibold text-amber-900">Nach Datenquelle</h3>
          <p className="text-sm text-amber-800">
            Keine Quellenaufteilung im Snapshot — bitte Briefing neu generieren (
            <code className="rounded bg-amber-100 px-1">python -m app.jobs.cli generate-briefing</code>
            ).
          </p>
        </section>
      ) : null}

      {(content.top_countries?.length ?? 0) > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 font-semibold text-slate-900">Top-Länder</h3>
          <ul className="space-y-2">
            {content.top_countries.map((country) => (
              <li
                key={country.code}
                className="flex items-center justify-between text-sm"
              >
                <span className="text-slate-700">{country.code}</span>
                <span className="font-medium text-slate-900">{country.count}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {content.affected_regions.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 font-semibold text-slate-900">Betroffene Regionen</h3>
          <ul className="space-y-2">
            {content.affected_regions.map((r) => (
              <li
                key={r.region}
                className="flex items-center justify-between text-sm"
              >
                <span className="text-slate-700">
                  {r.region}{" "}
                  <span className="text-slate-400">({r.max_severity})</span>
                </span>
                <span className="font-medium text-slate-900">{r.alert_count}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {content.major_events.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 font-semibold text-slate-900">Wesentliche Ereignisse</h3>
          <ul className="space-y-3">
            {content.major_events.map((event) => (
              <li key={event.alert_id} className="text-sm">
                <Link
                  href={`/alerts/${event.alert_id}`}
                  className="font-medium text-blue-700 hover:underline"
                >
                  {event.title}
                </Link>
                <p className="text-slate-500">
                  {event.severity} ·{" "}
                  {sourceLabel(event.source as Parameters<typeof sourceLabel>[0])}
                  {event.region ? ` · ${event.region}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {content.cross_border_patterns.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 font-semibold text-slate-900">
            {isLlm ? "Cross-Alert-Muster" : "Muster (Beobachtungen)"}
          </h3>
          <ul className="space-y-3">
            {content.cross_border_patterns.map((p, i) => (
              <li key={i} className="text-sm text-slate-700">
                <p>{p.description}</p>
                <p className="mt-1 text-xs text-slate-400">
                  Typ: {p.type} · Vertrauen: {p.confidence}
                  {p.alert_ids.length > 0 && (
                    <>
                      {" · "}
                      Quellen:{" "}
                      {p.alert_ids.slice(0, 3).map((id, j) => (
                        <span key={id}>
                          {j > 0 && ", "}
                          <Link href={`/alerts/${id}`} className="text-blue-600 hover:underline">
                            {id.slice(0, 8)}…
                          </Link>
                        </span>
                      ))}
                      {p.alert_ids.length > 3 && ` (+${p.alert_ids.length - 3})`}
                    </>
                  )}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {content.trend_anomalies.length > 0 && (
        <section className="rounded-lg border border-orange-200 bg-orange-50 p-4">
          <h3 className="mb-3 font-semibold text-orange-900">Trend-Anomalien</h3>
          <ul className="space-y-2">
            {content.trend_anomalies.map((a) => (
              <li key={`${a.dimension}-${a.key}`} className="text-sm text-orange-800">
                {a.dimension === "global"
                  ? "Global"
                  : `${a.dimension}: ${a.key}`}
                : {a.current_count} aktiv (Ø7d: {a.rolling_avg}, Faktor: {a.ratio}×)
              </li>
            ))}
          </ul>
        </section>
      )}

      <ImplicationsSection implications={content.potential_implications} />

      {content.observed_events && content.observed_events.items.length > 0 && (
        <ObservedEventsSectionView section={content.observed_events} />
      )}

      {content.verified_exposure && content.verified_exposure.items.length > 0 && (
        <VerifiedExposureSectionView section={content.verified_exposure} />
      )}

      {content.evidence_gaps && content.evidence_gaps.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-2 font-semibold text-slate-900">Evidenzlücken</h3>
          <p className="mb-3 text-xs text-slate-500">
            Fehlende oder unvollständige Daten in der Analysegrundlage.
          </p>
          <ul className="list-inside list-disc space-y-1 text-sm text-slate-600">
            {content.evidence_gaps.map((gap, i) => (
              <li key={i}>{gap}</li>
            ))}
          </ul>
        </section>
      )}

      {content.limitations.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <h3 className="mb-2 font-semibold text-slate-700">Einschränkungen</h3>
          <ul className="list-inside list-disc space-y-1 text-sm text-slate-600">
            {content.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </section>
      )}

      {content.source_alert_ids.length > 0 && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-2 font-semibold text-slate-900">Quell-Warnungen</h3>
          <p className="mb-2 text-xs text-slate-500">
            {content.source_alert_ids.length} Warnung(en) als Datenbasis für dieses Briefing.
          </p>
          <div className="flex flex-wrap gap-2">
            {content.source_alert_ids.slice(0, 12).map((id) => (
              <Link
                key={id}
                href={`/alerts/${id}`}
                className="rounded bg-slate-100 px-2 py-1 text-xs text-blue-700 hover:bg-slate-200"
              >
                {id.slice(0, 8)}…
              </Link>
            ))}
            {content.source_alert_ids.length > 12 && (
              <span className="px-2 py-1 text-xs text-slate-400">
                +{content.source_alert_ids.length - 12} weitere
              </span>
            )}
          </div>
        </section>
      )}

      <SourceHealthPanel
        sources={sources}
        demoMode={demoMode}
        showcaseMode={showcaseMode}
      />

      <div className="rounded-lg border border-slate-200 bg-slate-100 p-4 text-sm text-slate-600">
        <strong>Disclaimer:</strong>{" "}
        {isLlm
          ? "KI-generierte Interpretation aus öffentlichen Warnmeldungen — keine amtliche Warnung. Muster sind Beobachtungen, keine Kausalitätsnachweise. Implikationen sind Hypothesen, keine Prognosen."
          : "Regelbasierte Zusammenfassung aus öffentlichen Warnmeldungen — keine amtlichen Bewertungen. Implikationen sind konservative Hypothesen, keine Prognosen."}
      </div>
    </div>
  );
}

function ObservedEventsSectionView({
  section,
}: {
  section: NonNullable<Briefing["content"]["observed_events"]>;
}) {
  return (
    <section className="rounded-lg border border-blue-200 bg-blue-50 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="font-semibold text-blue-900">Observed Events</h3>
        <span className="text-xs text-blue-600">
          Vertrauen: {CONFIDENCE_LABELS[section.confidence] ?? section.confidence}
        </span>
      </div>
      <p className="mb-3 text-sm text-blue-800">{section.summary}</p>
      <ul className="space-y-2">
        {section.items.map((item) => (
          <li key={item.canonical_event_id} className="text-sm text-blue-900">
            <span className="font-medium">{item.event_title}</span>
            <span className="text-blue-600">
              {" "}
              · {item.severity} · {item.observed_count} Observed Event(s)
              {(item.sources?.length ?? 0) > 0 && <> · {item.sources.join(", ")}</>}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function VerifiedExposureSectionView({
  section,
}: {
  section: NonNullable<Briefing["content"]["verified_exposure"]>;
}) {
  return (
    <section className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="font-semibold text-emerald-900">Verifizierte Exposure</h3>
        <span className="text-xs text-emerald-600">
          Vertrauen: {CONFIDENCE_LABELS[section.confidence] ?? section.confidence}
        </span>
      </div>
      <p className="mb-3 text-sm text-emerald-800">{section.summary}</p>
      <ul className="space-y-2">
        {section.items.map((item, i) => (
          <li key={`${item.event_id}-${item.asset_name}-${i}`} className="text-sm text-emerald-900">
            <span className="font-medium">{item.asset_name}</span>
            <span className="text-emerald-600">
              {" "}
              ({item.asset_type}) · {item.exposure_type} · Ereignis: {item.event_title}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ImplicationsSection({
  implications,
}: {
  implications: Briefing["content"]["potential_implications"];
}) {
  const domains = [
    { key: "economy" as const, label: "Wirtschaft" },
    { key: "logistics" as const, label: "Logistik" },
    { key: "infrastructure" as const, label: "Infrastruktur" },
    { key: "technology" as const, label: "Technologie" },
    { key: "finance" as const, label: "Finanzen" },
  ];
  const hasAny = domains.some((d) => (implications[d.key]?.length ?? 0) > 0);
  if (!hasAny) return null;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-1 font-semibold text-slate-900">
        Mögliche Implikationen (Hypothesen)
      </h3>
      <p className="mb-3 text-xs text-slate-500">
        Konservative Ableitungen aus Kategorien — keine verifizierten Auswirkungen.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        {domains.map(
          (d) =>
            (implications[d.key]?.length ?? 0) > 0 && (
              <div key={d.key}>
                <h4 className="text-sm font-medium text-slate-800">{d.label}</h4>
                <ul className="mt-1 list-inside list-disc text-sm text-slate-600">
                  {(implications[d.key] ?? []).map((item, i) => (
                    <li key={i}>{item}</li>
                  ))}
                </ul>
              </div>
            ),
        )}
      </div>
    </section>
  );
}

const DEFAULT_LIVE_SOURCES = ["nina", "gdacs", "noaa"];

function SourceHealthPanel({
  sources,
  demoMode,
  showcaseMode,
}: {
  sources: SourceInfo[];
  demoMode: boolean;
  showcaseMode: boolean;
}) {
  if (sources.length === 0) return null;

  const fixtureSources = sources.filter((s) => s.ingest_mode === "fixture");
  const hasSourcesLiveFixture =
    !demoMode && !showcaseMode && fixtureSources.some((s) => !DEFAULT_LIVE_SOURCES.includes(s.id));

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-1 font-semibold text-slate-900">Quellen-Gesundheit</h3>
      <p className="mb-3 text-xs text-slate-500">
        Erreichbarkeit und Datenmodus jeder angebundenen Quelle.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
              <th scope="col" className="pb-2 pr-4 font-medium">
                Quelle
              </th>
              <th scope="col" className="pb-2 pr-4 font-medium">
                Datenmodus
              </th>
              <th scope="col" className="pb-2 pr-4 font-medium">
                Status
              </th>
              <th scope="col" className="pb-2 font-medium">
                Letzter Abruf
              </th>
            </tr>
          </thead>
          <tbody>
            {sources.map((src) => (
              <tr key={src.id} className="border-b border-slate-100 last:border-0">
                <td className="py-2 pr-4 text-slate-700">{src.name}</td>
                <td className="py-2 pr-4">
                  {src.ingest_mode ? (
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${ingestModeBadgeClass(src.ingest_mode)}`}
                      title={ingestModeTooltip(src.ingest_mode)}
                    >
                      <span
                        className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                          src.ingest_mode === "showcase"
                            ? "bg-violet-500"
                            : src.ingest_mode === "fixture"
                              ? "bg-amber-500"
                              : "bg-emerald-500"
                        }`}
                        aria-hidden
                      />
                      {ingestModeLabel(src.ingest_mode)}
                    </span>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
                <td className="py-2 pr-4">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${sourceHealthBadgeClass(src.healthy)}`}
                    title={
                      src.healthy
                        ? "Letzter Abruf oder Health-Check erfolgreich"
                        : "Quelle nicht erreichbar oder Fixture fehlt"
                    }
                  >
                    <span
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                        src.healthy ? "bg-green-500" : "bg-red-500"
                      }`}
                      aria-hidden
                    />
                    {sourceHealthLabel(src.healthy)}
                  </span>
                </td>
                <td className="py-2 text-slate-500">{formatDateTime(src.last_fetch)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 space-y-2 rounded-md bg-slate-50 p-3 text-xs text-slate-600">
        <div>
          <p className="font-medium text-slate-700">Datenmodus</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            <li>
              <strong>Live-Daten</strong> — Abruf von der echten externen API
            </li>
            <li>
              <strong>Demo-Daten (Fixture)</strong> — lokale JSON-Testdateien, kein Live-Abruf
            </li>
            <li>
              <strong>Showcase</strong> — kuratierte Demo-Szenarien für Präsentationen
            </li>
          </ul>
        </div>
        <div>
          <p className="font-medium text-slate-700">Status</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            <li>
              <strong>Erreichbar</strong> — letzter Abruf oder Health-Check erfolgreich
            </li>
            <li>
              <strong>Nicht erreichbar</strong> — API antwortet nicht oder Demo-Datei fehlt
            </li>
          </ul>
        </div>
        {demoMode && (
          <p className="text-amber-800">
            <strong>Hinweis:</strong> DEMO_MODE ist aktiv — alle Quellen verwenden Demo-Daten
            (Fixtures), unabhängig von SOURCES_LIVE.
          </p>
        )}
        {showcaseMode && (
          <p className="text-violet-800">
            <strong>Hinweis:</strong> SHOWCASE_MODE ist aktiv — kuratierte Demo-Szenarien statt
            Live- oder Fixture-Daten.
          </p>
        )}
        {hasSourcesLiveFixture && (
          <p className="text-amber-800">
            <strong>Hinweis:</strong> Quellen wie USGS, EONET, NOAA SWPC und NASA FIRMS zeigen
            „Demo-Daten“, weil sie nicht in <code className="rounded bg-amber-100 px-1">SOURCES_LIVE</code>{" "}
            enthalten sind (Standard: nina, gdacs, noaa). Für Live-Abruf z. B.{" "}
            <code className="rounded bg-amber-100 px-1">SOURCES_LIVE=nina,gdacs,noaa,usgs,eonet</code>{" "}
            setzen.
          </p>
        )}
      </div>
    </section>
  );
}

function ingestModeTooltip(mode: string | null | undefined): string {
  if (mode === "live") return "Daten werden von der echten externen API abgerufen";
  if (mode === "fixture") return "Daten stammen aus lokalen JSON-Demo-Dateien";
  if (mode === "showcase") return "Kuratierte Demo-Szenarien für Präsentationen";
  return "";
}

function StatsFallback({ stats }: { stats: Stats }) {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-3 font-semibold text-slate-900">Nach Kategorie</h3>
        <ul className="space-y-2">
          {Object.entries(stats.by_category)
            .sort(([, a], [, b]) => b - a)
            .map(([cat, count]) => (
              <li key={cat} className="flex items-center justify-between text-sm">
                <span className="text-slate-700">
                  {categoryLabel(cat as Parameters<typeof categoryLabel>[0])}
                </span>
                <span className="font-medium text-slate-900">{count}</span>
              </li>
            ))}
        </ul>
      </section>
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-3 font-semibold text-slate-900">Nach Datenquelle</h3>
        <ul className="space-y-2">
          {Object.entries(stats.by_source ?? {})
            .sort(([, a], [, b]) => b - a)
            .map(([src, count]) => (
              <li key={src} className="flex items-center justify-between text-sm">
                <span className="text-slate-700">
                  {sourceLabel(src as Parameters<typeof sourceLabel>[0])}
                </span>
                <span className="font-medium text-slate-900">{count}</span>
              </li>
            ))}
        </ul>
      </section>
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-3 font-semibold text-slate-900">Nach Schweregrad</h3>
        <ul className="space-y-2">
          {Object.entries(stats.by_severity)
            .sort(([, a], [, b]) => b - a)
            .map(([sev, count]) => (
              <li key={sev} className="flex items-center justify-between text-sm">
                <span className="capitalize text-slate-700">{sev}</span>
                <span className="font-medium text-slate-900">{count}</span>
              </li>
            ))}
        </ul>
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-3xl font-bold text-slate-900">{value}</p>
    </div>
  );
}
