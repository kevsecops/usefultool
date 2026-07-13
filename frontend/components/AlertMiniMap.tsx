"use client";

import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import type { Alert } from "@/types/alert";
import { severityColor } from "@/lib/format";

interface AlertMiniMapProps {
  alert: Alert;
  height?: string;
}

function getCenter(alert: Alert): [number, number] | null {
  if (alert.longitude != null && alert.latitude != null) {
    return [alert.longitude, alert.latitude];
  }
  if (alert.geometry?.type === "Point") {
    const coords = (alert.geometry as GeoJSON.Point).coordinates;
    return [coords[0], coords[1]];
  }
  return null;
}

export function AlertMiniMap({ alert, height = "240px" }: AlertMiniMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const center = getCenter(alert);
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
        layers: [
          {
            id: "osm",
            type: "raster",
            source: "osm",
          },
        ],
      },
      center: center ?? [10, 50],
      zoom: center ? 8 : 3,
      interactive: true,
      attributionControl: false,
    });

    mapRef.current = map;

    map.on("load", () => {
      if (alert.geometry) {
        map.addSource("alert-geometry", {
          type: "geojson",
          data: {
            type: "Feature",
            geometry: alert.geometry,
            properties: {},
          },
        });
        const layerType =
          alert.geometry.type === "Polygon" ||
          alert.geometry.type === "MultiPolygon"
            ? "fill"
            : "circle";
        if (layerType === "fill") {
          map.addLayer({
            id: "alert-fill",
            type: "fill",
            source: "alert-geometry",
            paint: {
              "fill-color": severityColor(alert.severity),
              "fill-opacity": 0.35,
            },
          });
          map.addLayer({
            id: "alert-outline",
            type: "line",
            source: "alert-geometry",
            paint: {
              "line-color": severityColor(alert.severity),
              "line-width": 2,
            },
          });
        } else {
          map.addLayer({
            id: "alert-point",
            type: "circle",
            source: "alert-geometry",
            paint: {
              "circle-radius": 8,
              "circle-color": severityColor(alert.severity),
            },
          });
        }
        const bounds = new maplibregl.LngLatBounds();
        const extendBounds = (coords: unknown) => {
          if (Array.isArray(coords)) {
            if (typeof coords[0] === "number") {
              bounds.extend(coords as [number, number]);
            } else {
              coords.forEach(extendBounds);
            }
          }
        };
        if (alert.geometry.type === "Point") {
          bounds.extend(
            (alert.geometry as GeoJSON.Point).coordinates as [number, number],
          );
        } else {
          extendBounds((alert.geometry as GeoJSON.Polygon).coordinates);
        }
        if (!bounds.isEmpty()) {
          map.fitBounds(bounds, { padding: 40, maxZoom: 10 });
        }
      } else if (center) {
        new maplibregl.Marker({ color: severityColor(alert.severity) })
          .setLngLat(center)
          .addTo(map);
      }
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [alert]);

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div ref={containerRef} style={{ height }} className="w-full" />
      <p className="border-t border-slate-100 px-3 py-2 text-xs text-slate-400">
        © OpenStreetMap contributors
      </p>
    </div>
  );
}
