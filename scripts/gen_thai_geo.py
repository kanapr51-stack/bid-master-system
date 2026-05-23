"""Generate thai-geo-data.ts from the downloaded CSV."""
import csv, sys

with open('data/thai_geo_raw.csv', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

geo = {}
for r in rows:
    prov  = r['province'].strip()
    dist  = r['district'].strip()
    tambon = r['subdistrict'].strip()
    lat_s = r['latitude'].strip()
    lng_s = r['longitude'].strip()
    lat = float(lat_s) if lat_s and lat_s != 'null' else None
    lng = float(lng_s) if lng_s and lng_s != 'null' else None
    if prov not in geo:
        geo[prov] = {}
    if dist not in geo[prov]:
        geo[prov][dist] = []
    geo[prov][dist].append({'name': tambon, 'lat': lat, 'lng': lng})

# Fill null coords with district centroid
for prov, districts in geo.items():
    for dist_name, tambons in districts.items():
        valid = [t for t in tambons if t['lat'] is not None]
        if valid:
            avg_lat = round(sum(t['lat'] for t in valid) / len(valid), 4)
            avg_lng = round(sum(t['lng'] for t in valid) / len(valid), 4)
        else:
            avg_lat, avg_lng = 13.7563, 100.5018
        for t in tambons:
            if t['lat'] is None:
                t['lat'] = avg_lat
                t['lng'] = avg_lng

def esc(s):
    return s.replace("'", "\\'")

def fmt_tambon(t):
    return "{ name: '" + esc(t['name']) + "', lat: " + str(t['lat']) + ", lng: " + str(t['lng']) + " }"

lines = []
lines.append("// AUTO-GENERATED from data.go.th via spicydog/thailand-province-district-subdistrict-zipcode-latitude-longitude")
lines.append("// 7,426 tambons, 928 districts, 77 provinces — do not edit manually")
lines.append("")
lines.append("export type ThaiDistrict = { name: string; lat: number; lng: number; tambons: { name: string; lat: number; lng: number }[] };")
lines.append("export type ThaiGeo = Record<string, ThaiDistrict[]>;")
lines.append("")
lines.append("const THAI_GEO_DATA: ThaiGeo = {")

for prov, districts in geo.items():
    lines.append("  '" + esc(prov) + "': [")
    for dist_name, tambons in districts.items():
        avg_lat = round(sum(t['lat'] for t in tambons) / len(tambons), 4)
        avg_lng = round(sum(t['lng'] for t in tambons) / len(tambons), 4)
        tambons_part = ', '.join(fmt_tambon(t) for t in tambons)
        lines.append("    { name: '" + esc(dist_name) + "', lat: " + str(avg_lat) + ", lng: " + str(avg_lng) + ", tambons: [" + tambons_part + "] },")
    lines.append("  ],")

lines.append("};")
lines.append("")
lines.append("export default THAI_GEO_DATA;")

output = '\n'.join(lines)

with open('data/thai_geo_data_ts.txt', 'w', encoding='utf-8') as f:
    f.write(output)

sys.stderr.write(f"Lines: {len(lines)}\n")
sys.stderr.write(f"File size: {len(output.encode('utf-8')) // 1024} KB\n")
# Sample
sys.stderr.write(lines[9][:160] + '\n')
sys.stderr.write(lines[-4][:160] + '\n')
