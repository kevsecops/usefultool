"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { Alert, AlertFilters } from "@/types/alert";
import type { CanonicalEvent, ObservedEvent } from "@/types/events";
import type { ExposureAsset } from "@/types/exposure";
import { Filters } from "@/components/Filters";
import { LayerControls, DEFAULT_LAYER_VISIBILITY } from "@/components/LayerControls";
import type { LayerVisibility } from "@/components/LayerControls";
import { filtersFromSearchParams } from "@/lib/filters";
import { AlertMap } from "@/components/AlertMap";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function buildQuery(filters: AlertFilters): string {
  const params = new URLSearchParams();
  if (filters.source) params.set("source", filters.source);
  if (filters.country) params.set("country", filters.country);
  if (filters.category) params.set("category", filters.category);
  if (filters.severity) params.set("severity", filters.severity);
  params.set("active", String(filters.active ?? true));
  params.set("limit", "200");
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

function MapContent() {
  const searchParams = useSearchParams();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [canonicalEvents, setCanonicalEvents] = useState<CanonicalEvent[]>([]);
  const [observedEvents, setObservedEvents] = useState<ObservedEvent[]>([]);
  const [assets, setAssets] = useState<ExposureAsset[]>([]);
  const [layerVisibility, setLayerVisibility] = useState<LayerVisibility>(
    DEFAULT_LAYER_VISIBILITY,
  );
  const [showcaseMode, setShowcaseMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const filterKey = searchParams.toString();

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      const filters = filtersFromSearchParams(
        Object.fromEntries(searchParams.entries()),
        { limit: 200 },
      );

      try {
        let alertsRes: Response;
        try {
          [alertsRes] = await Promise.all([
            fetch(`${API_URL}/api/v1/alerts${buildQuery({ ...filters, limit: 200 })}`),
          ]);
        } catch {
          throw new Error(
            `Backend nicht erreichbar unter ${API_URL} — läuft \`docker compose up\`?`,
          );
        }

        const [eventsRes, observedRes, assetsRes, healthRes] = await Promise.all([
          fetch(`${API_URL}/api/v1/events?active=true&limit=100`),
          fetch(`${API_URL}/api/v1/observed-events?active=true&limit=100`),
          fetch(`${API_URL}/api/v1/assets?limit=200`),
          fetch(`${API_URL}/health`),
        ]);

        if (!alertsRes.ok) {
          throw new Error(
            alertsRes.status >= 500
              ? `Backend-Fehler (${alertsRes.status}) — Datenbank-Schema prüfen: docker compose restart backend`
              : `API-Fehler ${alertsRes.status}`,
          );
        }

        const [alertsData, eventsData, observedData, assetsData, healthData] =
          await Promise.all([
            alertsRes.json(),
            eventsRes.ok ? eventsRes.json() : { items: [] },
            observedRes.ok ? observedRes.json() : { items: [] },
            assetsRes.ok ? assetsRes.json() : { items: [] },
            healthRes.ok ? healthRes.json() : { showcase_mode: false },
          ]);

        if (!cancelled) {
          setAlerts(alertsData.items);
          setCanonicalEvents(eventsData.items ?? []);
          setObservedEvents(observedData.items ?? []);
          setAssets(assetsData.items ?? []);
          setShowcaseMode(
            (healthData as { showcase_mode?: boolean }).showcase_mode ?? false,
          );
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Laden fehlgeschlagen");
          setAlerts([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [filterKey, searchParams]);

  return (
    <div className="space-y-4">
      <LayerControls
        visibility={layerVisibility}
        onChange={setLayerVisibility}
        showcaseMode={showcaseMode}
      />
      <Filters />
      {loading && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
          Kartendaten werden geladen…
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}
      <AlertMap
        alerts={alerts}
        canonicalEvents={canonicalEvents}
        observedEvents={observedEvents}
        assets={assets}
        layerVisibility={layerVisibility}
        showcaseMode={showcaseMode}
      />
    </div>
  );
}

export function MapPageClient() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Kartenansicht</h1>
        <p className="mt-1 text-slate-600">
          Multi-Layer-Karte mit Warnungen, Events, Observed Events und Exposure-Assets.
        </p>
      </div>
      <Suspense
        fallback={<div className="h-96 animate-pulse rounded-lg bg-slate-100" />}
      >
        <MapContent />
      </Suspense>
    </div>
  );
}
