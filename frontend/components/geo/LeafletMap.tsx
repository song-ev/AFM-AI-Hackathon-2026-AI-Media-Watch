"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

// Leaflet's default marker icons reference files by URL that bundlers break.
// Bundle the dependency's icons locally instead of requesting a CDN.
const DefaultIcon = L.icon({
  iconUrl: markerIcon.src,
  iconRetinaUrl: markerIcon2x.src,
  shadowUrl: markerShadow.src,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

const TILE_URL = process.env.NEXT_PUBLIC_MAP_TILE_URL ?? "";
const TILE_ATTRIBUTION = process.env.NEXT_PUBLIC_MAP_ATTRIBUTION ?? "";

export interface MapPoint {
  lat: number;
  lon: number;
  label?: string;
  region?: string;
  risk?: number;
  username?: string;
  platform?: string;
  caption?: string;
  count?: number;
}

function riskColor(risk: number): string {
  if (risk >= 75) return "#dc2626"; // red
  if (risk >= 50) return "#f59e0b"; // amber
  if (risk > 0) return "#eab308"; // yellow
  return "#3b82f6"; // blue (no risk score)
}

function esc(s: unknown): string {
  return String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string)
  );
}

interface LeafletMapProps {
  points: MapPoint[];
  /** Single-point pin mode vs. multi-point risk-bubbles mode. */
  mode?: "pin" | "bubbles";
  height?: number;
  zoom?: number;
}

/**
 * Map built on the raw Leaflet API (not react-leaflet). react-leaflet's
 * MapContainer double-initialises under React 18 StrictMode / Fast Refresh
 * ("Map container is already initialized"). Driving Leaflet imperatively with a
 * single init effect — create on mount, `map.remove()` on cleanup — makes
 * initialisation idempotent and StrictMode-safe.
 */
export default function LeafletMap({
  points,
  mode = "pin",
  height = 260,
  zoom = 6,
}: LeafletMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  // Create the map exactly once per mount; tear it down fully on unmount.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    // Defensive: if a previous Leaflet instance left its id on this node
    // (HMR edge cases), clear it before re-initialising.
    if ((el as unknown as { _leaflet_id?: number })._leaflet_id) {
      (el as unknown as { _leaflet_id?: number })._leaflet_id = undefined;
    }

    const map = L.map(el, { scrollWheelZoom: true }).setView(
      [48.0196, 66.9237], // Kazakhstan centroid
      zoom
    );
    if (TILE_URL) {
      L.tileLayer(TILE_URL, {
        attribution: TILE_ATTRIBUTION,
        maxZoom: 19,
      }).addTo(map);
    }
    mapRef.current = map;
    layerRef.current = L.layerGroup().addTo(map);

    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // (Re)draw markers whenever the data or mode changes.
  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;

    layer.clearLayers();

    points.forEach((p) => {
      if (mode === "pin") {
        const marker = L.marker([p.lat, p.lon], { icon: DefaultIcon });
        marker.bindPopup(
          `<div style="font-size:13px"><b>${esc(p.label || p.region)}</b>` +
            (p.caption ? `<br/><span style="opacity:.7">${esc(p.caption)}</span>` : "") +
            `</div>`
        );
        layer.addLayer(marker);
      } else {
        const risk = p.risk ?? 0;
        const radius = p.count
          ? Math.min(8 + p.count * 3, 28)
          : Math.max(7, (risk / 100) * 22);
        const color = riskColor(risk);
        const cm = L.circleMarker([p.lat, p.lon], {
          radius,
          color,
          fillColor: color,
          fillOpacity: 0.55,
          weight: 1.5,
        });
        cm.bindPopup(
          `<div style="font-size:13px"><b>${esc(p.label || p.region)}</b>` +
            (p.count != null ? `<br/>Видео: ${esc(p.count)}` : "") +
            (p.risk != null ? `<br/>Макс. риск: ${Math.round(p.risk)}` : "") +
            (p.username ? `<br/><span style="opacity:.7">@${esc(p.username)} · ${esc(p.platform)}</span>` : "") +
            `</div>`
        );
        layer.addLayer(cm);
      }
    });

    if (points.length === 1) {
      map.setView([points[0].lat, points[0].lon], 11, { animate: true });
    } else if (points.length > 1) {
      const bounds = L.latLngBounds(
        points.map((p) => [p.lat, p.lon] as [number, number])
      );
      map.fitBounds(bounds.pad(0.25), { animate: true });
    }
    // Leaflet may mis-measure size if the container animated in; nudge it.
    setTimeout(() => map.invalidateSize(), 0);
  }, [points, mode]);

  return (
    <div
      ref={containerRef}
      style={{ height, width: "100%", borderRadius: 12, zIndex: 0 }}
      className="bg-muted/40"
    />
  );
}
