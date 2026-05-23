"""
test_province_extractor.py — วัด precision/recall ของ extractor กับ data จริง

Ground truth = พิกัด GPS ของงาน (field แขวง/ตำบล = POINT(lon lat) ใน CGD)
  → reverse-geocode เป็นจังหวัด "ที่ตั้งงานจริง" (nearest tambon centroid)
  → เทียบกับผลของ extract_province(sub_name, project_name)

Metrics:
  coverage  = ทำนายไม่ว่าง / ทั้งหมด
  precision = ทำนายถูก / ทำนายไม่ว่าง   ← critical (ว่างดีกว่าผิด)
"""
import sys
import csv
import json
import math
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import province_extractor as pe  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = Path(__file__).parent.parent / "data"
ENV_FILE = Path(__file__).parent.parent / ".env"
API_URL = "https://opend.data.go.th/get-ckan/datastore_search"
RESOURCE_ID = "e4eaa1b4-eb1a-4534-b227-988ee25b898d"


def load_token():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("OPEND_USER_TOKEN="):
            return line.split("=", 1)[1].strip()


def build_revgeo():
    """list ของ (lat, lon, province) สำหรับ nearest-neighbor"""
    pts = []
    for r in csv.DictReader((DATA_DIR / "thai_geo_raw.csv").open(encoding="utf-8")):
        try:
            pts.append((float(r["latitude"]), float(r["longitude"]), r["province"]))
        except (ValueError, KeyError):
            continue
    return pts


def revgeo(lat, lon, pts):
    best_p, best_d = None, 1e18
    for plat, plon, prov in pts:
        d = (plat - lat) ** 2 + (plon - lon) ** 2
        if d < best_d:
            best_d, best_p = d, prov
    return best_p


def fetch_sample(token, n=2000, province=None):
    headers = {"api-key": token}
    params = {"resource_id": RESOURCE_ID, "limit": n}
    if province:
        params["filters"] = json.dumps({"จังหวัด": province}, ensure_ascii=False)
    r = requests.get(API_URL, headers=headers, params=params, timeout=60)
    r.raise_for_status()
    return r.json()["result"]["records"]


def parse_point(s):
    if not s or not s.startswith("POINT"):
        return None
    try:
        inner = s[s.index("(") + 1:s.index(")")]
        lon, lat = inner.split()
        lat, lon = float(lat), float(lon)
        if 5 < lat < 21 and 97 < lon < 106:  # Thailand bbox
            return lat, lon
    except (ValueError, IndexError):
        pass
    return None


def evaluate(records, pts, label):
    total = correct = wrong = empty = no_truth = 0
    mismatches = []
    for rec in records:
        pt = parse_point(rec.get("แขวง/ตำบล", ""))
        if not pt:
            no_truth += 1
            continue
        true_prov = revgeo(pt[0], pt[1], pts)
        sub = (rec.get("ชื่อหน่วยงานย่อย") or "").strip()
        proj = (rec.get("ชื่อโครงการ") or "").strip()
        pred = pe.extract_province(sub, proj)
        total += 1
        if not pred:
            empty += 1
        elif pred == true_prov:
            correct += 1
        else:
            wrong += 1
            if len(mismatches) < 12:
                mismatches.append((pred, true_prov, sub[:30], proj[:40]))

    nonempty = correct + wrong
    cov = nonempty / total if total else 0
    prec = correct / nonempty if nonempty else 0
    print(f"\n=== {label} (มี ground-truth {total} records) ===")
    print(f"  coverage  : {cov:.1%}  (ทำนายไม่ว่าง {nonempty}/{total})")
    print(f"  precision : {prec:.1%}  (ถูก {correct} / ผิด {wrong})")
    print(f"  ว่าง       : {empty}")
    if mismatches:
        print(f"  --- ตัวอย่างที่ผิด ---")
        for pred, tru, sub, proj in mismatches:
            print(f"    pred={pred} จริง={tru} | {sub} | {proj}")
    return cov, prec


def main():
    token = load_token()
    pe._CACHE.clear()
    pts = build_revgeo()
    print(f"reverse-geocoder: {len(pts)} จุด")

    # Test A: target provinces (Phase 1) — cache ควรช่วย
    for prov in ["นครพนม", "บึงกาฬ"]:
        recs = fetch_sample(token, 1500, province=prov)
        evaluate(recs, pts, f"จังหวัดเป้าหมาย {prov}")

    # Test B: nationwide random — วัด general precision (cache ไม่ช่วย)
    recs = fetch_sample(token, 2000)
    evaluate(recs, pts, "สุ่มทั่วประเทศ (file-1)")


if __name__ == "__main__":
    main()
