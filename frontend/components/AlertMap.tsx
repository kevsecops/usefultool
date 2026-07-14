"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import Supercluster from "supercluster";
import Link from "next/link";
import type { Alert, Severity } from "@/types/alert";
import type { CanonicalEvent, ObservedEvent } from "@/types/events";
import type { ExposureAsset } from "@/types/exposure";
import type { LayerVisibility } from "@/components/LayerControls";
import { severityColor, severityLabel, sourceLabel, ingestModeLabel } from "@/lib/format";
import { sanitizeToPlainText } from "@/lib/sanitize";

interface AlertMapProps {
  alerts: Alert[];
  canonicalEvents?: CanonicalEvent[];
  observedEvents?: ObservedEvent[];
  assets?: ExposureAsset[];
  layerVisibility?: LayerVisibility;
  showcaseMode?: boolean;
}

interface PointProperties {
  layerType: string;
  itemId: string;
  severity?: Severity;
  title: string;
  source?: string;
  assetType?: string;
  cluster?: boolean;
  cluster_id?: number;
  point_count?: number;
  point_count_abbreviated?: string | number;
}

type MapFeature = GeoJSON.Feature<GeoJSON.Point, PointProperties>;

const LAYER_COLORS: Record<string, string> = {
  alert: "#f97316",
  canonical: "#7c3aed",
  earthquake: "#dc2626",
  fire: "#ea580c",
  natural: "#2563eb",
  space: "#9333ea",
  port: "#0891b2",
  airport: "#0d9488",
  power_plant: "#ca8a04",
};

function coordsFromGeometry(geometry?: GeoJSON.Geometry | null): [number, number] | null {
  if (!geometry) return null;
  if (geometry.type === "Point") {
    const c = geometry.coordinates;
    return [c[0], c[1]];
  }
  return null;
}

function alertToPoint(alert: Alert): MapFeature | null {
  let lng = alert.longitude;
  let lat = alert.latitude;
  if ((lng == null || lat == null) && alert.geometry?.type === "Point") {
    const coords = (alert.geometry as GeoJSON.Point).coordinates;
    lng = coords[0];
    lat = coords[1];
  }
  if (lng == null || lat == null) return null;
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [lng, lat] },
    properties: {
      layerType: "alert",
      itemId: alert.id,
      severity: alert.severity,
      title: alert.title,
      source: alert.source,
    },
  };
}

function eventToPoint(
  event: CanonicalEvent | ObservedEvent,
  layerType: string,
): MapFeature | null {
  let lng: number | null | undefined =
    "longitude" in event ? event.longitude : null;
  let lat: number | null | undefined =
    "latitude" in event ? event.latitude : null;
  const coords = coordsFromGeometry(event.geometry ?? undefined);
  if (coords) {
    lng = coords[0];
    lat = coords[1];
  }
  if (lng == null || lat == null) return null;
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [lng, lat] },
    properties: {
      layerType,
      itemId: event.id,
      severity: event.severity,
      title: event.title,
      source: "source" in event ? event.source : undefined,
    },
  };
}

function assetToPoint(asset: ExposureAsset): MapFeature | null {
  if (asset.latitude == null || asset.longitude == null) return null;
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [asset.longitude, asset.latitude] },
    properties: {
      layerType: asset.asset_type,
      itemId: asset.id,
      title: asset.name,
      assetType: asset.asset_type,
    },
  };
}

function polygonFeatures(alerts: Alert[]): GeoJSON.Feature[] {
  return alerts
    .filter(
      (a) =>
        a.geometry &&
        (a.geometry.type === "Polygon" || a.geometry.type === "MultiPolygon"),
    )
    .map((alert) => ({
      type: "Feature" as const,
      geometry: alert.geometry!,
      properties: {
        layerType: "alert",
        itemId: alert.id,
        severity: alert.severity,
        title: alert.title,
        source: alert.source,
      },
    }));
}

function observedLayerType(event: ObservedEvent): string | null {
  if (event.source === "usgs") return "earthquake";
  if (event.source === "firms") return "fire";
  if (event.source === "eonet") return "natural";
  if (event.source === "noaa_swpc") return "space";
  return null;
}

export function AlertMap({
  alerts,
  canonicalEvents = [],
  observedEvents = [],
  assets = [],
  layerVisibility,
  showcaseMode = false,
}: AlertMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const clusterRef = useRef<Supercluster | null>(null);
  const dataRef = useRef({ alerts, canonicalEvents, observedEvents, assets });
  const initializedRef = useRef(false);
  const initialFitDoneRef = useRef(false);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<CanonicalEvent | null>(null);
  const [selectedObserved, setSelectedObserved] = useState<ObservedEvent | null>(null);
  const [selectedAsset, setSelectedAsset] = useState<ExposureAsset | null>(null);

  dataRef.current = { alerts, canonicalEvents, observedEvents, assets };

  const visibility = layerVisibility ?? {
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

  const updateClusters = useCallback((map: maplibregl.Map) => {
    const cluster = clusterRef.current;
    if (!cluster || !map.getSource("alerts-cluster")) return;
    const bounds = map.getBounds();
    const zoom = Math.floor(map.getZoom());
    const clusters = cluster.getClusters(
      [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()],
      zoom,
    );
    const source = map.getSource("alerts-cluster") as maplibregl.GeoJSONSource;
    source.setData({ type: "FeatureCollection", features: clusters });
  }, []);

  const updateMapData = useCallback(
    (map: maplibregl.Map) => {
      const cluster = clusterRef.current;
      if (!cluster) return;

      const { alerts: a, canonicalEvents: ce, observedEvents: oe, assets: ast } =
        dataRef.current;

      const alertPoints = visibility.alerts
        ? a.map(alertToPoint).filter(Boolean)
        : [];
      cluster.load(alertPoints as MapFeature[]);

      const polygonSource = map.getSource("alerts-polygons") as maplibregl.GeoJSONSource;
      if (polygonSource) {
        polygonSource.setData({
          type: "FeatureCollection",
          features: visibility.alerts ? polygonFeatures(a) : [],
        });
      }
      updateClusters(map);

      const canonicalPts = visibility.canonicalEvents
        ? ce.map((e) => eventToPoint(e, "canonical")).filter(Boolean)
        : [];
      const observedPts: MapFeature[] = [];
      for (const ev of oe) {
        const lt = observedLayerType(ev);
        if (
          (lt === "earthquake" && visibility.earthquakes) ||
          (lt === "fire" && visibility.fireClusters) ||
          (lt === "natural" && visibility.naturalEvents) ||
          (lt === "space" && visibility.spaceWeather)
        ) {
          const pt = eventToPoint(ev, lt);
          if (pt) observedPts.push(pt);
        }
      }

      const assetPts: MapFeature[] = [];
      for (const asset of ast) {
        if (
          (asset.asset_type === "port" && visibility.ports) ||
          (asset.asset_type === "airport" && visibility.airports) ||
          (asset.asset_type === "power_plant" && visibility.powerPlants)
        ) {
          const pt = assetToPoint(asset);
          if (pt) assetPts.push(pt);
        }
      }

      const setSource = (id: string, features: MapFeature[]) => {
        const src = map.getSource(id) as maplibregl.GeoJSONSource | undefined;
        if (src) src.setData({ type: "FeatureCollection", features });
      };

      setSource("canonical-events", canonicalPts as MapFeature[]);
      setSource("observed-events", observedPts);
      setSource("exposure-assets", assetPts as MapFeature[]);

      if (!initialFitDoneRef.current) {
        const allCoords = [
          ...(alertPoints as MapFeature[]),
          ...(canonicalPts as MapFeature[]),
          ...observedPts,
          ...(assetPts as MapFeature[]),
        ].map((f) => f.geometry.coordinates as [number, number]);
        if (allCoords.length > 0) {
          const bounds = new maplibregl.LngLatBounds();
          allCoords.forEach((c) => bounds.extend(c));
          map.fitBounds(bounds, { padding: 60, maxZoom: 8 });
          initialFitDoneRef.current = true;
        }
      }
    },
    [updateClusters, visibility],
  );

  useEffect(() => {
    if (!containerRef.current || initializedRef.current) return;
    initializedRef.current = true;

    const cluster = new Supercluster<PointProperties>({ radius: 50, maxZoom: 14 });
    clusterRef.current = cluster;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: [10, 30],
      zoom: 2,
    });

    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("load", () => {
      const empty = { type: "FeatureCollection" as const, features: [] };

      map.addSource("alerts-cluster", { type: "geojson", data: empty });
      map.addSource("alerts-polygons", { type: "geojson", data: empty });
      map.addSource("canonical-events", { type: "geojson", data: empty });
      map.addSource("observed-events", { type: "geojson", data: empty });
      map.addSource("exposure-assets", { type: "geojson", data: empty });

      map.addLayer({
        id: "alert-polygons-fill",
        type: "fill",
        source: "alerts-polygons",
        paint: {
          "fill-color": [
            "match", ["get", "severity"],
            "minor", severityColor("minor"),
            "moderate", severityColor("moderate"),
            "severe", severityColor("severe"),
            "extreme", severityColor("extreme"),
            severityColor("unknown"),
          ],
          "fill-opacity": 0.3,
        },
      });

      map.addLayer({
        id: "alert-clusters",
        type: "circle",
        source: "alerts-cluster",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#1e293b",
          "circle-radius": ["step", ["get", "point_count"], 18, 10, 22, 50, 28],
          "circle-opacity": 0.85,
        },
      });

      map.addLayer({
        id: "alert-points",
        type: "circle",
        source: "alerts-cluster",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-radius": 7,
          "circle-color": [
            "match", ["get", "severity"],
            "minor", severityColor("minor"),
            "moderate", severityColor("moderate"),
            "severe", severityColor("severe"),
            "extreme", severityColor("extreme"),
            severityColor("unknown"),
          ],
          "circle-stroke-width": 1,
          "circle-stroke-color": "#ffffff",
        },
      });

      map.addLayer({
        id: "canonical-points",
        type: "circle",
        source: "canonical-events",
        paint: {
          "circle-radius": 10,
          "circle-color": LAYER_COLORS.canonical,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
        },
      });

      map.addLayer({
        id: "observed-points",
        type: "circle",
        source: "observed-events",
        paint: {
          "circle-radius": 6,
          "circle-color": [
            "match", ["get", "layerType"],
            "earthquake", LAYER_COLORS.earthquake,
            "fire", LAYER_COLORS.fire,
            "natural", LAYER_COLORS.natural,
            "space", LAYER_COLORS.space,
            "#6b7280",
          ],
          "circle-stroke-width": 1,
          "circle-stroke-color": "#ffffff",
        },
      });

      map.addLayer({
        id: "asset-points",
        type: "circle",
        source: "exposure-assets",
        paint: {
          "circle-radius": 4,
          "circle-color": [
            "match", ["get", "layerType"],
            "port", LAYER_COLORS.port,
            "airport", LAYER_COLORS.airport,
            "power_plant", LAYER_COLORS.power_plant,
            "#94a3b8",
          ],
          "circle-opacity": 0.9,
        },
      });

      updateMapData(map);
    });

    map.on("moveend", () => updateClusters(map));

    const handleClick = (
      e: maplibregl.MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] },
    ) => {
      const feature = e.features?.[0];
      if (!feature) return;
      const props = feature.properties as PointProperties;

      if (props.cluster && props.cluster_id != null) {
        const clusterInstance = clusterRef.current;
        if (!clusterInstance) return;
        const expansionZoom = Math.min(
          clusterInstance.getClusterExpansionZoom(props.cluster_id),
          20,
        );
        map.easeTo({
          center: (feature.geometry as GeoJSON.Point).coordinates as [number, number],
          zoom: expansionZoom,
        });
        return;
      }

      const { alerts: a, canonicalEvents: ce, observedEvents: oe, assets: ast } =
        dataRef.current;

      setSelectedAlert(null);
      setSelectedEvent(null);
      setSelectedObserved(null);
      setSelectedAsset(null);

      if (props.layerType === "alert") {
        const alert = a.find((x) => x.id === props.itemId);
        if (alert) setSelectedAlert(alert);
      } else if (props.layerType === "canonical") {
        const ev = ce.find((x) => x.id === props.itemId);
        if (ev) setSelectedEvent(ev);
      } else if (["earthquake", "fire", "natural", "space"].includes(props.layerType)) {
        const ev = oe.find((x) => x.id === props.itemId);
        if (ev) setSelectedObserved(ev);
      } else {
        const asset = ast.find((x) => x.id === props.itemId);
        if (asset) setSelectedAsset(asset);
      }
    };

    const layers = [
      "alert-clusters",
      "alert-points",
      "alert-polygons-fill",
      "canonical-points",
      "observed-points",
      "asset-points",
    ];
    for (const layer of layers) {
      map.on("click", layer, handleClick);
      map.on("mouseenter", layer, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; });
    }

    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
      clusterRef.current = null;
      initializedRef.current = false;
      initialFitDoneRef.current = false;
    };
  }, [updateClusters, updateMapData]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    updateMapData(map);
  }, [alerts, canonicalEvents, observedEvents, assets, layerVisibility, updateMapData]);

  const closePopup = () => {
    setSelectedAlert(null);
    setSelectedEvent(null);
    setSelectedObserved(null);
    setSelectedAsset(null);
  };

  return (
    <div className="relative">
      {showcaseMode && (
        <div className="absolute right-4 top-4 z-10 rounded-full bg-violet-600 px-3 py-1 text-xs font-medium text-white shadow">
          Showcase / Demo
        </div>
      )}

      <div
        ref={containerRef}
        className="h-[calc(100vh-12rem)] min-h-[600px] w-full rounded-lg border border-slate-200"
      />

      {selectedAlert && (
        <MapPopup onClose={closePopup}>
          <PopupBadges
            severity={selectedAlert.severity}
            source={sourceLabel(selectedAlert.source)}
            ingestMode={selectedAlert.ingest_mode}
          />
          <h3 className="pr-6 font-semibold text-slate-900">{selectedAlert.title}</h3>
          {selectedAlert.description && (
            <p className="mt-1 text-sm text-slate-600">
              {sanitizeToPlainText(selectedAlert.description).slice(0, 120)}…
            </p>
          )}
          <Link href={`/alerts/${selectedAlert.id}`} className="mt-3 inline-block text-sm font-medium text-blue-600 hover:underline">
            Details anzeigen →
          </Link>
        </MapPopup>
      )}

      {selectedEvent && (
        <MapPopup onClose={closePopup}>
          <span className="mb-2 inline-flex rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-800">
            Canonical Event
          </span>
          <h3 className="pr-6 font-semibold text-slate-900">{selectedEvent.title}</h3>
          <p className="mt-1 text-sm text-slate-500">
            {severityLabel(selectedEvent.severity)} · {selectedEvent.member_count} Quelle(n)
          </p>
          <Link href={`/events/${selectedEvent.id}`} className="mt-3 inline-block text-sm font-medium text-blue-600 hover:underline">
            Event-Details →
          </Link>
        </MapPopup>
      )}

      {selectedObserved && (
        <MapPopup onClose={closePopup}>
          <span className="mb-2 inline-flex rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">
            Observed Event · {selectedObserved.source}
          </span>
          <h3 className="pr-6 font-semibold text-slate-900">{selectedObserved.title}</h3>
          <p className="mt-1 text-sm text-slate-500">{severityLabel(selectedObserved.severity)}</p>
        </MapPopup>
      )}

      {selectedAsset && (
        <MapPopup onClose={closePopup}>
          <span className="mb-2 inline-flex rounded-full bg-teal-100 px-2 py-0.5 text-xs font-medium text-teal-800">
            {selectedAsset.asset_type}
          </span>
          <h3 className="pr-6 font-semibold text-slate-900">{selectedAsset.name}</h3>
          <p className="mt-1 text-sm text-slate-500">
            {selectedAsset.country_code} · {selectedAsset.importance_level}
          </p>
        </MapPopup>
      )}

      <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
        {Object.entries(LAYER_COLORS).map(([key, color]) => (
          <span key={key} className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
            {key}
          </span>
        ))}
      </div>
    </div>
  );
}

function MapPopup({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <aside className="absolute bottom-4 left-4 z-10 w-80 max-w-[calc(100%-2rem)] rounded-lg border border-slate-200 bg-white p-4 shadow-lg">
      <button
        type="button"
        onClick={onClose}
        className="absolute right-2 top-2 text-slate-400 hover:text-slate-600"
        aria-label="Schließen"
      >
        ×
      </button>
      {children}
    </aside>
  );
}

function PopupBadges({
  severity,
  source,
  ingestMode,
}: {
  severity: Severity;
  source: string;
  ingestMode?: string;
}) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <span
        className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium text-white"
        style={{ backgroundColor: severityColor(severity) }}
      >
        {severityLabel(severity)}
      </span>
      <span className="text-xs text-slate-500">{source}</span>
      {ingestMode && (
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
            ingestMode === "showcase"
              ? "bg-violet-100 text-violet-800"
              : ingestMode === "fixture"
                ? "bg-amber-100 text-amber-800"
                : "bg-emerald-100 text-emerald-800"
          }`}
        >
          {ingestModeLabel(ingestMode as "live" | "fixture" | "showcase")}
        </span>
      )}
    </div>
  );
}
