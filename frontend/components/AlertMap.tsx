"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import Supercluster from "supercluster";
import Link from "next/link";
import type { Alert, Severity } from "@/types/alert";
import { severityColor, severityLabel, sourceLabel } from "@/lib/format";
import { sanitizeToPlainText } from "@/lib/sanitize";

interface AlertMapProps {
  alerts: Alert[];
}

interface AlertFeatureProperties {
  alertId: string;
  severity: Severity;
  title: string;
  source: string;
  cluster?: boolean;
  cluster_id?: number;
  point_count?: number;
  point_count_abbreviated?: string | number;
}

type AlertFeature = GeoJSON.Feature<GeoJSON.Point, AlertFeatureProperties>;

function alertToPoint(alert: Alert): AlertFeature | null {
  let lng: number | null = alert.longitude;
  let lat: number | null = alert.latitude;

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
      alertId: alert.id,
      severity: alert.severity,
      title: alert.title,
      source: alert.source,
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
        alertId: alert.id,
        severity: alert.severity,
        title: alert.title,
        source: alert.source,
      },
    }));
}

export function AlertMap({ alerts }: AlertMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const clusterRef = useRef<Supercluster | null>(null);
  const alertsRef = useRef(alerts);
  const initializedRef = useRef(false);
  const initialFitDoneRef = useRef(false);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);

  alertsRef.current = alerts;

  const updateClusters = useCallback((map: maplibregl.Map) => {
    const cluster = clusterRef.current;
    if (!cluster || !map.getSource("alerts-cluster")) return;

    const bounds = map.getBounds();
    const zoom = Math.floor(map.getZoom());
    const clusters = cluster.getClusters(
      [
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
      ],
      zoom,
    );

    const source = map.getSource("alerts-cluster") as maplibregl.GeoJSONSource;
    source.setData({ type: "FeatureCollection", features: clusters });
  }, []);

  const updateAlertData = useCallback(
    (map: maplibregl.Map, nextAlerts: Alert[]) => {
      const cluster = clusterRef.current;
      if (!cluster) return;

      const points = nextAlerts.map(alertToPoint).filter(Boolean) as AlertFeature[];
      const polygons = polygonFeatures(nextAlerts);
      cluster.load(points);

      const polygonSource = map.getSource(
        "alerts-polygons",
      ) as maplibregl.GeoJSONSource;
      if (polygonSource) {
        polygonSource.setData({
          type: "FeatureCollection",
          features: polygons,
        });
      }

      updateClusters(map);

      if (!initialFitDoneRef.current && points.length > 0) {
        const bounds = new maplibregl.LngLatBounds();
        points.forEach((p) => {
          bounds.extend(p.geometry.coordinates as [number, number]);
        });
        map.fitBounds(bounds, { padding: 60, maxZoom: 8 });
        initialFitDoneRef.current = true;
      }
    },
    [updateClusters],
  );

  useEffect(() => {
    if (!containerRef.current || initializedRef.current) return;
    initializedRef.current = true;

    const cluster = new Supercluster<AlertFeatureProperties>({
      radius: 50,
      maxZoom: 14,
    });
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
      map.addSource("alerts-cluster", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addSource("alerts-polygons", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "alert-polygons-fill",
        type: "fill",
        source: "alerts-polygons",
        paint: {
          "fill-color": [
            "match",
            ["get", "severity"],
            "minor",
            severityColor("minor"),
            "moderate",
            severityColor("moderate"),
            "severe",
            severityColor("severe"),
            "extreme",
            severityColor("extreme"),
            severityColor("unknown"),
          ],
          "fill-opacity": 0.3,
        },
      });

      map.addLayer({
        id: "alert-polygons-outline",
        type: "line",
        source: "alerts-polygons",
        paint: {
          "line-color": [
            "match",
            ["get", "severity"],
            "minor",
            severityColor("minor"),
            "moderate",
            severityColor("moderate"),
            "severe",
            severityColor("severe"),
            "extreme",
            severityColor("extreme"),
            severityColor("unknown"),
          ],
          "line-width": 2,
        },
      });

      map.addLayer({
        id: "alert-clusters",
        type: "circle",
        source: "alerts-cluster",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#1e293b",
          "circle-radius": [
            "step",
            ["get", "point_count"],
            18,
            10,
            22,
            50,
            28,
          ],
          "circle-opacity": 0.85,
        },
      });

      map.addLayer({
        id: "alert-cluster-count",
        type: "symbol",
        source: "alerts-cluster",
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-size": 12,
          "text-font": ["Open Sans Bold"],
        },
        paint: { "text-color": "#ffffff" },
      });

      map.addLayer({
        id: "alert-points",
        type: "circle",
        source: "alerts-cluster",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-radius": 7,
          "circle-color": [
            "match",
            ["get", "severity"],
            "minor",
            severityColor("minor"),
            "moderate",
            severityColor("moderate"),
            "severe",
            severityColor("severe"),
            "extreme",
            severityColor("extreme"),
            severityColor("unknown"),
          ],
          "circle-stroke-width": 1,
          "circle-stroke-color": "#ffffff",
        },
      });

      updateAlertData(map, alertsRef.current);
    });

    map.on("moveend", () => {
      updateClusters(map);
    });

    const handleClick = (
      e: maplibregl.MapMouseEvent & {
        features?: maplibregl.MapGeoJSONFeature[];
      },
    ) => {
      const feature = e.features?.[0];
      if (!feature) return;

      const props = feature.properties as AlertFeatureProperties;

      if (props.cluster && props.cluster_id != null) {
        const clusterInstance = clusterRef.current;
        if (!clusterInstance) return;
        const expansionZoom = Math.min(
          clusterInstance.getClusterExpansionZoom(props.cluster_id),
          20,
        );
        map.easeTo({
          center: (feature.geometry as GeoJSON.Point).coordinates as [
            number,
            number,
          ],
          zoom: expansionZoom,
        });
        return;
      }

      const alert = alertsRef.current.find((a) => a.id === props.alertId);
      if (alert) setSelectedAlert(alert);
    };

    map.on("click", "alert-clusters", handleClick);
    map.on("click", "alert-points", handleClick);
    map.on("click", "alert-polygons-fill", handleClick);

    const setPointer = () => {
      map.getCanvas().style.cursor = "pointer";
    };
    const clearPointer = () => {
      map.getCanvas().style.cursor = "";
    };

    map.on("mouseenter", "alert-clusters", setPointer);
    map.on("mouseleave", "alert-clusters", clearPointer);
    map.on("mouseenter", "alert-points", setPointer);
    map.on("mouseleave", "alert-points", clearPointer);
    map.on("mouseenter", "alert-polygons-fill", setPointer);
    map.on("mouseleave", "alert-polygons-fill", clearPointer);

    const resizeObserver = new ResizeObserver(() => {
      map.resize();
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
      clusterRef.current = null;
      initializedRef.current = false;
      initialFitDoneRef.current = false;
    };
  }, [updateAlertData, updateClusters]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    updateAlertData(map, alerts);
  }, [alerts, updateAlertData]);

  return (
    <div className="relative">
      <div
        ref={containerRef}
        className="h-[calc(100vh-12rem)] min-h-[600px] w-full rounded-lg border border-slate-200"
      />

      {selectedAlert && (
        <aside className="absolute bottom-4 left-4 z-10 w-80 max-w-[calc(100%-2rem)] rounded-lg border border-slate-200 bg-white p-4 shadow-lg">
          <button
            type="button"
            onClick={() => setSelectedAlert(null)}
            className="absolute right-2 top-2 text-slate-400 hover:text-slate-600"
            aria-label="Schließen"
          >
            ×
          </button>
          <div className="mb-2 flex items-center gap-2">
            <span
              className="inline-flex rounded-full px-2 py-0.5 text-xs font-medium text-white"
              style={{
                backgroundColor: severityColor(selectedAlert.severity),
              }}
            >
              {severityLabel(selectedAlert.severity)}
            </span>
            <span className="text-xs text-slate-500">
              {sourceLabel(selectedAlert.source)}
            </span>
          </div>
          <h3 className="pr-6 font-semibold text-slate-900">
            {selectedAlert.title}
          </h3>
          {selectedAlert.description && (
            <p className="mt-1 text-sm text-slate-600">
              {sanitizeToPlainText(selectedAlert.description).slice(0, 120)}…
            </p>
          )}
          <Link
            href={`/alerts/${selectedAlert.id}`}
            className="mt-3 inline-block text-sm font-medium text-blue-600 hover:underline"
          >
            Details anzeigen →
          </Link>
        </aside>
      )}

      <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
        {(["minor", "moderate", "severe", "extreme", "unknown"] as Severity[]).map(
          (s) => (
            <span key={s} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: severityColor(s) }}
              />
              {severityLabel(s)}
            </span>
          ),
        )}
      </div>
    </div>
  );
}
