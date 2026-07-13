import type { Severity } from "@/types/alert";
import { severityColor } from "@/lib/format";

interface RiskScoreGaugeProps {
  score: number;
  size?: "sm" | "lg";
}

function scoreLabel(score: number): string {
  if (score >= 75) return "Kritisch";
  if (score >= 50) return "Erhöht";
  if (score >= 25) return "Moderat";
  return "Niedrig";
}

export function RiskScoreGauge({ score, size = "lg" }: RiskScoreGaugeProps) {
  const clamped = Math.max(0, Math.min(100, score));
  const rotation = (clamped / 100) * 180 - 90;
  const severity: Severity =
    clamped >= 75
      ? "extreme"
      : clamped >= 50
        ? "severe"
        : clamped >= 25
          ? "moderate"
          : "minor";
  const color = severityColor(severity);
  const isLarge = size === "lg";

  return (
    <div className={`flex flex-col items-center ${isLarge ? "gap-2" : "gap-1"}`}>
      <div
        className={`relative ${isLarge ? "h-32 w-64" : "h-20 w-40"} overflow-hidden`}
      >
        <div
          className={`absolute bottom-0 left-1/2 -translate-x-1/2 rounded-t-full border-[12px] border-slate-200 bg-slate-100 ${isLarge ? "h-32 w-64" : "h-20 w-40"}`}
        />
        <div
          className={`absolute bottom-0 left-1/2 origin-bottom -translate-x-1/2 ${isLarge ? "h-28 w-1" : "h-16 w-0.5"}`}
          style={{
            transform: `translateX(-50%) rotate(${rotation}deg)`,
            backgroundColor: color,
            transformOrigin: "bottom center",
          }}
        />
        <div
          className={`absolute bottom-0 left-1/2 -translate-x-1/2 rounded-full bg-slate-800 ${isLarge ? "h-4 w-4" : "h-3 w-3"}`}
        />
      </div>
      <div className="text-center">
        <p
          className={`font-bold ${isLarge ? "text-4xl" : "text-2xl"}`}
          style={{ color }}
        >
          {clamped}
        </p>
        <p className={`text-slate-500 ${isLarge ? "text-sm" : "text-xs"}`}>
          Global Risk Score — {scoreLabel(clamped)}
        </p>
      </div>
    </div>
  );
}
