import { Suspense } from "react";
import { getAlerts } from "@/lib/api";
import { filtersFromSearchParams, Filters } from "@/components/Filters";
import { AlertList } from "@/components/AlertList";

export const dynamic = "force-dynamic";

interface AlertsPageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export default async function AlertsPage({ searchParams }: AlertsPageProps) {
  const params = await searchParams;
  const filters = filtersFromSearchParams(params, { limit: 20 });
  const { items, total, limit, offset } = await getAlerts(filters);

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

      <Suspense fallback={<div className="h-64 animate-pulse rounded-lg bg-slate-100" />}>
        <AlertList
          alerts={items}
          total={total}
          limit={limit}
          offset={offset}
        />
      </Suspense>
    </div>
  );
}
