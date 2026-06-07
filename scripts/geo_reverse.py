"""geo_reverse.py — reverse-geocode พิกัด → (จังหวัด,อำเภอ,ตำบล) จาก thai_geo_raw.csv (self-contained).
ใช้แยกอำเภอเมื่อตำบลซ้ำ (intel ระดับท้องถิ่น). thai_geo_raw lat/lng ถูกต้อง (กทม. lat=13.75)."""
import csv
import math
from pathlib import Path

_CSV = Path(__file__).parent.parent / "data" / "thai_geo_raw.csv"
_POINTS = None   # list[(lat, lng, province, district, subdistrict)]


def _load():
    global _POINTS
    if _POINTS is None:
        pts = []
        with open(_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    pts.append((float(r["latitude"]), float(r["longitude"]),
                                r["province"], r["district"], r["subdistrict"]))
                except (ValueError, KeyError):
                    continue
        _POINTS = pts
    return _POINTS


def _haversine(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def reverse_geocode(lat, lng):
    """(province, amphoe, tambon, distance_km) ของ subdistrict centroid ใกล้สุด. None ถ้าพิกัดใช้ไม่ได้."""
    try:
        lat = float(lat); lng = float(lng)
    except (TypeError, ValueError):
        return None
    if not lat or not lng:
        return None
    best = None
    for plat, plng, prov, dist, sub in _load():
        d = _haversine(lat, lng, plat, plng)
        if best is None or d < best[3]:
            best = (prov, dist, sub, d)
    return best


def amphoes_of_tambon(province, tambon):
    """list อำเภอ (distinct) ที่มีตำบลชื่อนี้ในจังหวัด — ใช้เช็ค ambiguity. [] ถ้าไม่มี."""
    out = []
    for _lat, _lng, prov, dist, sub in _load():
        if prov == province and sub == tambon and dist not in out:
            out.append(dist)
    return out
