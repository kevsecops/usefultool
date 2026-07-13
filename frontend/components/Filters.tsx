"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";
import type { AlertFilters, AlertSource, Category, Severity } from "@/types/alert";
import { filtersFromSearchParams } from "@/lib/filters";

export { filtersFromSearchParams };

const SOURCES: { value: AlertSource; label: string }[] = [
  { value: "noaa", label: "NOAA/NWS" },
  { value: "nina", label: "NINA/BBK" },
  { value: "gdacs", label: "GDACS" },
];

const SEVERITIES: { value: Severity; label: string }[] = [
  { value: "extreme", label: "Extrem" },
  { value: "severe", label: "Schwer" },
  { value: "moderate", label: "Mittel" },
  { value: "minor", label: "Gering" },
  { value: "unknown", label: "Unbekannt" },
];

const CATEGORIES: { value: Category; label: string }[] = [
  { value: "weather", label: "Wetter" },
  { value: "flood", label: "Hochwasser" },
  { value: "wildfire", label: "Waldbrand" },
  { value: "earthquake", label: "Erdbeben" },
  { value: "volcano", label: "Vulkan" },
  { value: "tsunami", label: "Tsunami" },
  { value: "health", label: "Gesundheit" },
  { value: "civil", label: "Bevölkerungsschutz" },
  { value: "other", label: "Sonstiges" },
];

interface FiltersProps {
  showCountry?: boolean;
  className?: string;
}

export function Filters({ showCountry = true, className = "" }: FiltersProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const updateFilter = useCallback(
    (key: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value) {
        params.set(key, value);
      } else {
        params.delete(key);
      }
      if (key !== "offset" && key !== "page") {
        params.delete("offset");
        params.delete("page");
      }
      router.push(`?${params.toString()}`);
    },
    [router, searchParams],
  );

  const clearFilters = useCallback(() => {
    router.push("?");
  }, [router]);

  const current: AlertFilters = {
    source: (searchParams.get("source") as AlertSource) || undefined,
    country: searchParams.get("country") || undefined,
    category: (searchParams.get("category") as Category) || undefined,
    severity: (searchParams.get("severity") as Severity) || undefined,
    active: searchParams.get("active") !== "false",
  };

  const hasFilters =
    current.source ||
    current.country ||
    current.category ||
    current.severity ||
    searchParams.get("active") === "false";

  return (
    <div
      className={`flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 ${className}`}
    >
      <div className="flex flex-col gap-1">
        <label htmlFor="filter-source" className="text-xs font-medium text-slate-500">
          Quelle
        </label>
        <select
          id="filter-source"
          value={current.source ?? ""}
          onChange={(e) => updateFilter("source", e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
        >
          <option value="">Alle</option>
          {SOURCES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      {showCountry && (
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-country" className="text-xs font-medium text-slate-500">
            Land
          </label>
          <input
            id="filter-country"
            type="text"
            placeholder="z.B. US, DE"
            value={current.country ?? ""}
            onChange={(e) => updateFilter("country", e.target.value.toUpperCase())}
            className="w-24 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
        </div>
      )}

      <div className="flex flex-col gap-1">
        <label htmlFor="filter-category" className="text-xs font-medium text-slate-500">
          Kategorie
        </label>
        <select
          id="filter-category"
          value={current.category ?? ""}
          onChange={(e) => updateFilter("category", e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
        >
          <option value="">Alle</option>
          {CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="filter-severity" className="text-xs font-medium text-slate-500">
          Schweregrad
        </label>
        <select
          id="filter-severity"
          value={current.severity ?? ""}
          onChange={(e) => updateFilter("severity", e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
        >
          <option value="">Alle</option>
          {SEVERITIES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="filter-active" className="text-xs font-medium text-slate-500">
          Status
        </label>
        <select
          id="filter-active"
          value={current.active ? "true" : "false"}
          onChange={(e) => updateFilter("active", e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
        >
          <option value="true">Aktiv</option>
          <option value="false">Alle</option>
        </select>
      </div>

      {hasFilters && (
        <button
          type="button"
          onClick={clearFilters}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
        >
          Zurücksetzen
        </button>
      )}
    </div>
  );
}

