/**
 * GET /api/portal/road-distances?lat=X&lng=Y
 * Returns road distances (km) from the given point to all tambons within ~200km straight-line.
 * Keys: "province::district::tambon"
 * Results are cached to data/road_distance_cache.json to avoid redundant API calls.
 */
import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { distanceKm } from '@/lib/portal-data';
import THAI_GEO_DATA from '@/app/portal/thai-geo-data';

export const runtime = 'nodejs';

const CACHE_PATH = path.join(process.cwd(), '..', '..', 'data', 'road_distance_cache.json');
const BATCH = 25;
const PREFILTER_KM = 200;

type Cache = Record<string, Record<string, number>>;
type TambonData = { name: string; lat: number; lng: number };
type DistrictData = { name: string; lat: number; lng: number; tambons: TambonData[] };

function readCache(): Cache {
  try { return JSON.parse(fs.readFileSync(CACHE_PATH, 'utf-8')); }
  catch { return {}; }
}

function writeCache(data: Cache) {
  try { fs.writeFileSync(CACHE_PATH, JSON.stringify(data)); } catch {}
}

function cacheKey(lat: number, lng: number) {
  return `${lat.toFixed(3)}|${lng.toFixed(3)}`;
}

export async function GET(req: NextRequest) {
  const lat = parseFloat(req.nextUrl.searchParams.get('lat') ?? '');
  const lng = parseFloat(req.nextUrl.searchParams.get('lng') ?? '');
  if (isNaN(lat) || isNaN(lng)) {
    return NextResponse.json({ error: 'invalid coords' }, { status: 400 });
  }

  const key = cacheKey(lat, lng);
  const cache = readCache();
  if (cache[key]) {
    return NextResponse.json({ distances: cache[key], fromCache: true });
  }

  const apiKey = process.env.GOOGLE_MAPS_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: 'GOOGLE_MAPS_API_KEY not configured' }, { status: 500 });
  }

  // Pre-filter: tambons within PREFILTER_KM straight-line
  const candidates: { key: string; prov: string; district: string; name: string }[] = [];
  for (const [prov, districts] of Object.entries(THAI_GEO_DATA)) {
    for (const d of districts as DistrictData[]) {
      for (const t of d.tambons) {
        if (distanceKm(lat, lng, t.lat, t.lng) <= PREFILTER_KM) {
          candidates.push({
            key: `${prov}::${d.name}::${t.name}`,
            prov,
            district: d.name,
            name: t.name,
          });
        }
      }
    }
  }

  const results: Record<string, number> = {};

  for (let i = 0; i < candidates.length; i += BATCH) {
    const batch = candidates.slice(i, i + BATCH);
    // ใช้ชื่อตำบลจริง เพื่อให้ Google Maps route ไปที่เดียวกับที่ user ค้นหา
    const dests = batch.map(c =>
      encodeURIComponent(`ตำบล${c.name} อำเภอ${c.district} ${c.prov} Thailand`)
    ).join('|');
    const url = `https://maps.googleapis.com/maps/api/distancematrix/json` +
      `?origins=${lat},${lng}&destinations=${dests}&mode=driving&language=th&key=${apiKey}`;
    try {
      const res = await fetch(url);
      const json = await res.json() as {
        status: string;
        rows: { elements: { status: string; distance: { value: number } }[] }[];
      };
      if (json.status === 'OK') {
        json.rows[0].elements.forEach((el, idx) => {
          if (el.status === 'OK') results[batch[idx].key] = el.distance.value / 1000;
        });
      }
    } catch { /* skip batch, fallback to Haversine on client */ }
  }

  cache[key] = results;
  writeCache(cache);
  return NextResponse.json({ distances: results });
}
