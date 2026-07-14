"use client";

export interface LayerVisibility {
  alerts: boolean;
  canonicalEvents: boolean;
  earthquakes: boolean;
  fireClusters: boolean;
  naturalEvents: boolean;
  spaceWeather: boolean;
  ports: boolean;
  airports: boolean;
  powerPlants: boolean;
}

export const DEFAULT_LAYER_VISIBILITY: LayerVisibility = {
  alerts: true,
  canonicalEvents: true,
  earthquakes: false,
  fireClusters: false,
  naturalEvents: false,
  spaceWeather: false,
  ports: true,
  airports: true,
  powerPlants: false,
};

interface LayerControlsProps {
  visibility: LayerVisibility;
  onChange: (next: LayerVisibility) => void;
  showcaseMode?: boolean;
}

const LAYER_ITEMS: Array<{
  key: keyof LayerVisibility;
  label: string;
  color: string;
  group?: string;
}> = [
  { key: "alerts", label: "Warnungen", color: "#f97316", group: "core" },
  { key: "canonicalEvents", label: "Canonical Events", color: "#7c3aed", group: "core" },
  { key: "earthquakes", label: "Erdbeben (USGS)", color: "#dc2626", group: "observed" },
  { key: "fireClusters", label: "Fire Clusters (FIRMS)", color: "#ea580c", group: "observed" },
  { key: "naturalEvents", label: "Natural Events (EONET)", color: "#2563eb", group: "observed" },
  { key: "spaceWeather", label: "Space Weather (SWPC)", color: "#9333ea", group: "observed" },
  { key: "ports", label: "Häfen", color: "#0891b2", group: "assets" },
  { key: "airports", label: "Flughäfen", color: "#0d9488", group: "assets" },
  { key: "powerPlants", label: "Kraftwerke", color: "#ca8a04", group: "assets" },
];

export function LayerControls({
  visibility,
  onChange,
  showcaseMode = false,
}: LayerControlsProps) {
  const toggle = (key: keyof LayerVisibility) => {
    onChange({ ...visibility, [key]: !visibility[key] });
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900">Karten-Layer</h2>
        {showcaseMode && (
          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800">
            Showcase / Demo
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {LAYER_ITEMS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => toggle(item.key)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
              visibility[item.key]
                ? "border-slate-300 bg-slate-50 text-slate-900"
                : "border-slate-200 bg-white text-slate-400"
            }`}
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{
                backgroundColor: visibility[item.key] ? item.color : "#cbd5e1",
              }}
            />
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}
