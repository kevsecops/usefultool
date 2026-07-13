import { Suspense } from "react";
import { getAlerts, ApiError } from "@/lib/api";
import { filtersFromSearchParams } from "@/lib/filters";
import { Filters } from "@/components/Filters";
import { AlertList } from "@/components/AlertList";

export const dynamic = "force-dynamic";

interface AlertsPageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function AlertsPage({ searchParams }: AlertsPageProps) {
  const params = await searchParams;
  const filters = filtersFromSearchParams(params, { limit: 20 });

  let items: Awaited<ReturnType<typeof getAlerts>>["items"] = [];
  let total = 0;
  let limit = filters.limit ?? 20;
  let offset = filters.offset ?? 0;
  let error: string | null = null;

  try {
    const result = await getAlerts(filters);
    items = result.items;
    total = result.total;
    limit = result.limit;
    offset = result.offset;
  } catch (e) {
    error =
      e instanceof ApiError
        ? e.message
        : e instanceof Error
          ? e.message
          : "Warnungen konnten nicht geladen werden";
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Warnungsliste</h1>
        <p className="mt-1 text-slate-600">
          Sortiert nach Ausstellungsdatum (neueste zuerst).
        </p>
      </div>

      <Suspense fallback={<div className="h-20 animate-pulse rounded-lg bg-slate-100" />}>
        <Filters />
      </Suspense>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}. Stellen Sie sicher, dass die API unter{" "}
          {process.env.API_URL ??
            process.env.NEXT_PUBLIC_API_URL ??
            "http://localhost:8000"}{" "}
          erreichbar ist.
        </div>
      )}

      {!error && (
        <Suspense fallback={<div className="h-64 animate-pulse rounded-lg bg-slate-100" />}>
          <AlertList
            alerts={items}
            total={total}
            limit={limit}
            offset={offset}
          />
        </Suspense>
      )}
    </div>
  );
}
