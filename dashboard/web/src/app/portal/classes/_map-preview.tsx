'use client';

import { useEffect, useRef } from 'react';

interface MapPreviewProps {
  lat: number;
  lng: number;
  radiusKm: number;
}

export function MapPreview({ lat, lng, radiusKm }: MapPreviewProps) {
  const divRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import('leaflet').Map | null>(null);
  const circleRef = useRef<import('leaflet').Circle | null>(null);

  useEffect(() => {
    if (!divRef.current || typeof window === 'undefined') return;

    import('leaflet').then(L => {
      // Fix default icon paths broken by webpack
      delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
        iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
      });

      if (!mapRef.current && divRef.current) {
        mapRef.current = L.map(divRef.current, { zoomControl: true, scrollWheelZoom: false })
          .setView([lat, lng], 10);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
          maxZoom: 18,
        }).addTo(mapRef.current);
        L.marker([lat, lng]).addTo(mapRef.current);
      } else if (mapRef.current) {
        mapRef.current.setView([lat, lng], 10);
      }

      if (circleRef.current) circleRef.current.remove();
      if (radiusKm > 0 && mapRef.current) {
        circleRef.current = L.circle([lat, lng], {
          radius: radiusKm * 1000,
          color: '#C8A86A',
          fillColor: 'rgba(200, 168, 106, 0.15)',
          fillOpacity: 1,
          weight: 1.5,
        }).addTo(mapRef.current);
        mapRef.current.fitBounds(circleRef.current.getBounds(), { padding: [20, 20] });
      }
    });

    return () => {
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
    };
  }, [lat, lng, radiusKm]);

  return (
    <>
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
      <div ref={divRef} style={{ height: 200, borderRadius: 10, overflow: 'hidden', border: '1px solid var(--line)' }} />
    </>
  );
}
