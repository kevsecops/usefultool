import Link from "next/link";
import type { Alert } from "@/types/alert";
import {
  categoryLabel,
  formatDateTime,
  severityColor,
  severityLabel,
  sourceLabel,
  truncate,
} from "@/lib/format";
import { sanitizeToPlainText } from "@/lib/sanitize";

interface AlertCardProps {
  alert: Alert;
  compact?: boolean;
}

export function AlertCard({ alert, compact = false }: AlertCardProps) {
  const description = sanitizeToPlainText(alert.description);

  return (
    <Link
      href={`/alerts/${alert.id}`}
      className="block rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
    >
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span
          className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium text-white"
          style={{ backgroundColor: severityColor(alert.severity) }}
        >
          {severityLabel(alert.severity)}
        </span>
        <span className="text-xs text-slate-500">{sourceLabel(alert.source)}</span>
        {alert.country_code && (
          <span className="text-xs text-slate-500">{alert.country_code}</span>
        )}
        <span className="text-xs text-slate-400">
          {categoryLabel(alert.category)}
        </span>
      </div>
      <h3 className={`font-semibold text-slate-900 ${compact ? "text-sm" : "text-base"}`}>
        {alert.title}
      </h3>
      {!compact && description && (
        <p className="mt-1 text-sm text-slate-600">
          {truncate(description, 160)}
        </p>
      )}
      <p className="mt-2 text-xs text-slate-400">
        {formatDateTime(alert.issued_at)}
        {alert.expires_at && ` · bis ${formatDateTime(alert.expires_at)}`}
      </p>
    </Link>
  );
}
