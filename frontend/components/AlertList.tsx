"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { Alert } from "@/types/alert";
import {
  categoryLabel,
  formatDateTime,
  severityColor,
  severityLabel,
  sourceLabel,
} from "@/lib/format";

interface AlertListProps {
  alerts: Alert[];
  total: number;
  limit: number;
  offset: number;
  basePath?: string;
}

export function AlertList({
  alerts,
  total,
  limit,
  offset,
  basePath = "/alerts",
}: AlertListProps) {
  const searchParams = useSearchParams();
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  const pageHref = (page: number) => {
    const params = new URLSearchParams(searchParams.toString());
    if (page <= 1) {
      params.delete("page");
    } else {
      params.set("page", String(page));
    }
    const qs = params.toString();
    return qs ? `${basePath}?${qs}` : basePath;
  };

  if (alerts.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-slate-500">
        Keine Warnungen gefunden.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-slate-600">
                Quelle
              </th>
              <th className="px-4 py-3 text-left font-medium text-slate-600">
                Land
              </th>
              <th className="px-4 py-3 text-left font-medium text-slate-600">
                Typ
              </th>
              <th className="px-4 py-3 text-left font-medium text-slate-600">
                Schweregrad
              </th>
              <th className="px-4 py-3 text-left font-medium text-slate-600">
                Beginn
              </th>
              <th className="px-4 py-3 text-left font-medium text-slate-600">
                Ablauf
              </th>
              <th className="px-4 py-3 text-left font-medium text-slate-600">
                Status
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {alerts.map((alert) => (
              <tr key={alert.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link
                    href={`/alerts/${alert.id}`}
                    className="font-medium text-blue-600 hover:underline"
                  >
                    {sourceLabel(alert.source)}
                  </Link>
                </td>
                <td className="px-4 py-3 text-slate-700">
                  {alert.country_code ?? "—"}
                </td>
                <td className="px-4 py-3 text-slate-700">
                  {categoryLabel(alert.category)}
                </td>
                <td className="px-4 py-3">
                  <span
                    className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium text-white"
                    style={{ backgroundColor: severityColor(alert.severity) }}
                  >
                    {severityLabel(alert.severity)}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {formatDateTime(alert.starts_at ?? alert.issued_at)}
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {formatDateTime(alert.expires_at)}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                      alert.is_active
                        ? "bg-green-100 text-green-800"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {alert.is_active ? "Aktiv" : "Inaktiv"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-slate-600">
        <p>
          {total} Warnung{total === 1 ? "" : "en"} · Seite {currentPage} von{" "}
          {totalPages}
        </p>
        <div className="flex gap-2">
          {hasPrev && (
            <Link
              href={pageHref(currentPage - 1)}
              className="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-50"
            >
              Zurück
            </Link>
          )}
          {hasNext && (
            <Link
              href={pageHref(currentPage + 1)}
              className="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-50"
            >
              Weiter
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
