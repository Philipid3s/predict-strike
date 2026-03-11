import { useEffect, useMemo, useRef } from 'react';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Map as MapLibreMap, Marker as MapLibreMarker, Popup as MapLibrePopup, StyleSpecification } from 'maplibre-gl';
import { OPENSKY_BASES } from '../data/openskyBases';
import type { OpenSkyAnomaly } from '../types/api';

interface OpenSkyMapProps {
  anomalies: OpenSkyAnomaly[];
  selectedAnomalyId: string | null;
  onSelectAnomaly: (icao24: string) => void;
}

function formatPopupReason(reason: string) {
  if (reason === 'military_like_callsign') {
    return 'Military-like callsign';
  }
  if (reason === 'tanker_transport_pattern') {
    return 'Tanker / transport pattern';
  }
  if (reason === 'military_callsign_cluster') {
    return 'Military callsign cluster';
  }
  if (reason.startsWith('suspicious_region_concentration:')) {
    return `Cluster: ${reason.split(':')[1]}`;
  }
  if (reason.startsWith('military_airfield_departure:')) {
    return `Departure near ${reason.split(':')[1]}`;
  }
  return reason.replace(/_/g, ' ');
}

const OPENSTREETMAP_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: {
        'background-color': '#d7e3f0',
      },
    },
    {
      id: 'osm-tiles',
      type: 'raster',
      source: 'osm',
    },
  ],
};

const INITIAL_VIEW = {
  center: [18, 27] as [number, number],
  zoom: 1.55,
};

export function OpenSkyMap({ anomalies, selectedAnomalyId, onSelectAnomaly }: OpenSkyMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const anomalyMarkersRef = useRef<MapLibreMarker[]>([]);
  const baseMarkersRef = useRef<MapLibreMarker[]>([]);
  const popupsRef = useRef<MapLibrePopup[]>([]);
  const maplibreRef = useRef<typeof import('maplibre-gl') | null>(null);

  const positionedAnomalies = useMemo(
    () => anomalies.filter((anomaly) => anomaly.latitude !== null && anomaly.longitude !== null),
    [anomalies],
  );

  useEffect(() => {
    if (import.meta.env.MODE === 'test' || !containerRef.current || mapRef.current) {
      return;
    }

    let isMounted = true;
    let localMap: MapLibreMap | null = null;

    void import('maplibre-gl').then((maplibre) => {
      if (!isMounted || !containerRef.current) {
        return;
      }

      maplibreRef.current = maplibre;
      localMap = new maplibre.Map({
        container: containerRef.current,
        style: OPENSTREETMAP_STYLE,
        center: INITIAL_VIEW.center,
        zoom: INITIAL_VIEW.zoom,
        attributionControl: false,
        dragRotate: false,
        touchPitch: false,
      });

      localMap.addControl(new maplibre.NavigationControl({ showCompass: false }), 'top-right');
      mapRef.current = localMap;
    });

    return () => {
      isMounted = false;
      anomalyMarkersRef.current.forEach((marker) => marker.remove());
      anomalyMarkersRef.current = [];
      baseMarkersRef.current.forEach((marker) => marker.remove());
      baseMarkersRef.current = [];
      popupsRef.current.forEach((popup) => popup.remove());
      popupsRef.current = [];
      localMap?.remove();
      mapRef.current = null;
      maplibreRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current || !maplibreRef.current) {
      return;
    }

    const maplibre = maplibreRef.current;

    anomalyMarkersRef.current.forEach((marker) => marker.remove());
    anomalyMarkersRef.current = [];
    baseMarkersRef.current.forEach((marker) => marker.remove());
    baseMarkersRef.current = [];
    popupsRef.current.forEach((popup) => popup.remove());
    popupsRef.current = [];

    baseMarkersRef.current = OPENSKY_BASES.map((base) => {
      const markerElement = document.createElement('div');
      markerElement.className = 'maplibre-base-marker';
      markerElement.setAttribute('role', 'img');
      markerElement.setAttribute('aria-label', `Military base ${base.name}`);
      markerElement.title = `${base.name} - ${base.operator}`;

      const popup = new maplibre.Popup({
        closeButton: false,
        closeOnClick: false,
        closeOnMove: false,
        offset: 14,
      })
        .setLngLat([base.longitude, base.latitude])
        .setHTML(`
        <div class="maplibre-anomaly-popup maplibre-anomaly-popup--base">
          <span class="maplibre-anomaly-popup__eyebrow">Tracked Airfield</span>
          <strong>${base.name}</strong>
          <div class="maplibre-anomaly-popup__grid">
            <span>Country</span>
            <span>${base.country}</span>
            <span>Operator</span>
            <span>${base.operator}</span>
            <span>Position</span>
            <span>${base.latitude.toFixed(2)}, ${base.longitude.toFixed(2)}</span>
          </div>
        </div>
      `);
      popupsRef.current.push(popup);

      markerElement.addEventListener('mouseenter', () => popup.addTo(mapRef.current!));
      markerElement.addEventListener('mouseleave', () => popup.remove());

      return new maplibre.Marker({ element: markerElement, anchor: 'center' })
        .setLngLat([base.longitude, base.latitude])
        .setPopup(popup)
        .addTo(mapRef.current!);
    });

    anomalyMarkersRef.current = positionedAnomalies.map((anomaly) => {
      const markerElement = document.createElement('div');
      markerElement.className =
        anomaly.icao24 === selectedAnomalyId
          ? 'maplibre-anomaly-marker maplibre-anomaly-marker--selected'
          : 'maplibre-anomaly-marker';
      markerElement.setAttribute('role', 'button');
      markerElement.setAttribute('tabindex', '0');
      markerElement.setAttribute('aria-label', `Map marker ${anomaly.callsign ?? anomaly.icao24}`);
      markerElement.title = `${anomaly.callsign ?? anomaly.icao24} - ${anomaly.origin_country ?? 'Unknown origin'}`;

      const popup = new maplibre.Popup({
        closeButton: false,
        closeOnClick: false,
        closeOnMove: false,
        offset: 18,
      })
        .setLngLat([anomaly.longitude!, anomaly.latitude!])
        .setHTML(`
        <div class="maplibre-anomaly-popup">
          <span class="maplibre-anomaly-popup__eyebrow">Flagged Flight</span>
          <strong>${anomaly.callsign ?? anomaly.icao24}</strong>
          <div class="maplibre-anomaly-popup__grid">
            <span>Country</span>
            <span>${anomaly.origin_country ?? 'Unknown origin'}</span>
            <span>ICAO24</span>
            <span>${anomaly.icao24}</span>
            <span>Altitude</span>
            <span>${anomaly.baro_altitude ? `${Math.round(anomaly.baro_altitude)} m` : 'n/a'}</span>
            <span>Velocity</span>
            <span>${anomaly.velocity ? `${Math.round(anomaly.velocity)} m/s` : 'n/a'}</span>
            <span>Position</span>
            <span>${anomaly.latitude?.toFixed(2) ?? 'n/a'}, ${anomaly.longitude?.toFixed(2) ?? 'n/a'}</span>
          </div>
          <div class="maplibre-anomaly-popup__reasons">
            ${anomaly.reasons.map((reason) => `<span>${formatPopupReason(reason)}</span>`).join('')}
          </div>
        </div>
      `);
      popupsRef.current.push(popup);

      markerElement.addEventListener('mouseenter', () => popup.addTo(mapRef.current!));
      markerElement.addEventListener('mouseleave', () => popup.remove());
      markerElement.addEventListener('focus', () => popup.addTo(mapRef.current!));
      markerElement.addEventListener('blur', () => popup.remove());
      markerElement.addEventListener('click', () => onSelectAnomaly(anomaly.icao24));
      markerElement.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelectAnomaly(anomaly.icao24);
        }
      });

      return new maplibre.Marker({ element: markerElement, anchor: 'center' })
        .setLngLat([anomaly.longitude!, anomaly.latitude!])
        .setPopup(popup)
        .addTo(mapRef.current!);
    });
  }, [onSelectAnomaly, positionedAnomalies, selectedAnomalyId]);

  useEffect(() => {
    if (!mapRef.current || !maplibreRef.current) {
      return;
    }

    const selected = positionedAnomalies.find((anomaly) => anomaly.icao24 === selectedAnomalyId);
    if (!selected || selected.latitude === null || selected.longitude === null) {
      return;
    }

    mapRef.current.flyTo({
      center: [selected.longitude, selected.latitude],
      zoom: Math.max(mapRef.current.getZoom(), 4.2),
      speed: 0.8,
      curve: 1.2,
      essential: true,
    });
  }, [positionedAnomalies, selectedAnomalyId]);

  const handleResetView = () => {
    if (!mapRef.current || !maplibreRef.current) {
      return;
    }

    const maplibre = maplibreRef.current;

    if (!positionedAnomalies.length && !OPENSKY_BASES.length) {
      mapRef.current.flyTo({ center: INITIAL_VIEW.center, zoom: INITIAL_VIEW.zoom, essential: true });
      return;
    }

    const bounds = new maplibre.LngLatBounds();
    positionedAnomalies.forEach((anomaly) => {
      bounds.extend([anomaly.longitude!, anomaly.latitude!]);
    });
    OPENSKY_BASES.forEach((base) => {
      bounds.extend([base.longitude, base.latitude]);
    });
    mapRef.current.fitBounds(bounds, { padding: 48, maxZoom: 5.2, duration: 800 });
  };

  if (import.meta.env.MODE === 'test') {
    return (
      <div className="maplibre-map" data-testid="opensky-map">
        <div
          className="maplibre-map__canvas maplibre-map__canvas--fallback"
          role="img"
          aria-label="World map of current OpenSky flight anomalies"
        />
        <div className="maplibre-map__toolbar">
          <button className="maplibre-map__reset" type="button">
            Reset View
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="maplibre-map">
      <div ref={containerRef} className="maplibre-map__canvas" role="img" aria-label="World map of current OpenSky flight anomalies" />
      <div className="maplibre-map__toolbar">
        <button className="maplibre-map__reset" type="button" onClick={handleResetView}>
          Reset View
        </button>
      </div>
    </div>
  );
}
