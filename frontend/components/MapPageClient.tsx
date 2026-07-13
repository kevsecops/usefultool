"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { Alert, AlertFilters } from "@/types/alert";
import { Filters, filtersFromSearchParams } from "@/components/Filters";
import { AlertMap } from "@/components/AlertMap";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function buildQuery(filters: AlertFilters): string {
  const params = new URLSearchParams();
  if (filters.source) params.set("source", filters.source);
  if (filters.country) params.set("country", filters.country);
  if (filters.category) params.set("category", filters.category);
  if (filters.severity) params.set("severity", filters.severity);
  params.set("active", String(filters.active ?? true));
  if (filters.bounding_box) params.set("bounding_box", filters.bounding_box);
  params.set("limit", "200");
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

function MapContent() {
  const searchParams = useSearchParams();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bbox, setBbox] = useState<string | undefined>();

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
      const queryFilters: AlertFilters = { ...filters, limit: 200 };
      if (bbox) queryFilters.bounding_box = bbox;

      try {
        const res = await fetch(
          `${API_URL}/api/v1/alerts${buildQuery(queryFilters)}`,
        );
        if (!res.ok) throw new Error(`API error ${res.status}`);
        const data = await res.json();
        if (!cancelled) setAlerts(data.items);
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
  }, [filterKey, bbox, searchParams]);

  return (
    <div className="space-y-4">
      <Filters />
      {loading && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
          Warnungen werden geladen…
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}
      {!loading && !error && (
        <AlertMap alerts={alerts} onBoundsChange={setBbox} />
      )}
    </div>
  );
}

export function MapPageClient() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Kartenansicht</h1>
        <p className="mt-1 text-slate-600">
          Interaktive Weltkarte mit Warnungen nach Schweregrad. Klicken Sie auf
          Marker für Details.
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
