"""mine_vocab_gaps.py — ขุด candidate keyword จาก "ช่องโหว่" (offline, pythainlp).
gap = (a) UNKNOWN จ้างก่อสร้าง [classifier]  (b) จ้างก่อสร้างในตำบลเป้าหมาย ที่ matcher ไม่มี keyword.
กรองหนัก (เลข/สถานที่/stopword/generic/boilerplate/มีแล้ว) → uni+bigram freq>=FLOOR → merge เข้าคลัง + Sheet.
รัน: python scripts/mine_vocab_gaps.py
"""
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
from pythainlp.tokenize import word_tokenize
from pythainlp.corpus import thai_stopwords
from text_normalize import normalize_thai
from work_type_classifier import classify_work_type
from sheets_client import get_client

ROOT = Path(__file__).parent.parent
DB = ROOT / "data" / "winner_history.db"
VOCAB = ROOT / "config" / "construction_vocab.json"
SHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps"
FLOOR = 10
THAI = re.compile(r"^[ก-๙]+$")
NUM = re.compile(r"[0-9๐-๙]")
STOP = set(thai_stopwords())
GENERIC = set("""จ้าง โครงการ ก่อสร้าง ปรับปรุง ซ่อมแซม ซ่อม โดยวิธี วิธี เฉพาะเจาะจง ตกลงราคา ประกวดราคา
อิเล็กทรอนิกส์ สอบราคา คัดเลือก หมู่ ตำบล อำเภอ จังหวัด บ้าน ที่ แห่ง จำนวน ขนาด พร้อม ภายใน เพื่อ ของ และ
งาน เหมา ดำเนินการ ตาม แบบ รายการ ป้าย ประจำ ปีงบประมาณ งบประมาณ สาย เส้น หมู่ที่ ราย นาย นาง กว้าง ยาว
หนา เมตร พื้นที่ ระบบ ศูนย์ องค์การบริหารส่วนตำบล เทศบาล การ ความ โครง คสล
พัฒนา การพัฒนา การปรับปรุง โครงการปรับปรุง โครงการพัฒนา ราคา ตกลง ตกลงราคา วิธีตกลง สำหรับ บริเวณ
เทศบาลตำบล เขต ติดตั้ง วัด โรง กฟ จำหน่าย ขยาย ระบาย จัด จัดซื้อ ปรับ ภายในหมู่บ้าน ทาง ใหม่ เดิม""".split())
BOILER = set("""เศรษฐกิจพอเพียง ภัยแล้ง ยั่งยืน ส่งเสริมอาชีพ ส่งเสริม อาชีพ ฤดูแล้ง ปรัชญา ต้นทุน เก็บกัก
เพิ่มปริมาณ ท่วม อย่างยั่งยืน แนวปรัชญา การแก้ปัญหา ช่วงฤดูแล้ง ไว้ใช้ ตามแนว แห่ง""".split())


def place_stoplist(con):
    place = set()
    for prov, dist, sub in con.execute("SELECT DISTINCT province, district, subdistrict FROM winner_history"):
        for g in (prov, dist, sub):
            if g and "(" not in g and not re.match(r"^(POINT|LINE|POLY|MULTI)", g):
                place.add(g.strip())
                for t in word_tokenize(g, engine="newmm", keep_whitespace=False):
                    if len(t.strip()) >= 2:
                        place.add(t.strip())
    return place


def existing_terms():
    terms = set()
    wt = json.loads((ROOT / "config" / "work_type_keywords.json").read_text(encoding="utf-8"))
    for kws in wt["categories"].values():
        terms |= set(kws)
    terms |= set(wt["other_keywords"])
    mp = json.loads((ROOT / "config" / "matching_preferences.json").read_text(encoding="utf-8"))
    terms |= set(mp.get("keywords", []))
    return terms


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    mp = json.loads((ROOT / "config" / "matching_preferences.json").read_text(encoding="utf-8"))
    target_tb = set(mp.get("target_tambons", []))
    mkw = mp.get("keywords", [])
    place = place_stoplist(con)
    have = existing_terms()

    gap = []
    for rj, sub in con.execute("SELECT raw_json, subdistrict FROM winner_history"):
        d = json.loads(rj)
        if d.get("ชื่อประเภทโครงการ") != "จ้างก่อสร้าง":
            continue
        name = normalize_thai(d.get("ชื่อโครงการ") or "")
        if not name:
            continue
        is_unknown = classify_work_type(name)["primary"] == "UNKNOWN"
        in_target = (sub or "").strip() in target_tb
        no_mkw = in_target and not any(k in name for k in mkw)
        if is_unknown or no_mkw:
            src = "both" if (is_unknown and no_mkw) else ("classifier" if is_unknown else "matcher")
            gap.append((name, src))
    con.close()
    print(f"gap jobs: {len(gap)}")

    def keep(t):
        t = t.strip()
        return (len(t) >= 2 and THAI.match(t) and not NUM.search(t)
                and t not in STOP and t not in GENERIC and t not in BOILER
                and t not in place and t not in have)

    df, src_of, ex_of = Counter(), {}, {}
    for name, src in gap:
        toks = word_tokenize(name, engine="newmm", keep_whitespace=False)
        seen = set()
        for i, t in enumerate(toks):
            t = t.strip()
            if keep(t):
                seen.add(t)
            if i + 1 < len(toks):
                bg = t + toks[i + 1].strip()
                if (THAI.match(bg) and not NUM.search(bg) and bg not in have and len(bg) >= 4
                        and (keep(t) or keep(toks[i + 1])) and bg not in BOILER):
                    seen.add(bg)
        for s in seen:
            df[s] += 1
            src_of.setdefault(s, src)
            ex_of.setdefault(s, name[:70])

    cands = [(t, n) for t, n in df.most_common() if n >= FLOOR]
    print(f"candidate (freq>={FLOOR}): {len(cands)}")

    vocab = json.loads(VOCAB.read_text(encoding="utf-8"))
    by_term = {e["term"]: e for e in vocab["terms"]}
    added = 0
    for t, n in cands:
        if t in by_term:
            by_term[t]["freq"] = n
            continue
        by_term[t] = {"term": t, "freq": n, "examples": [ex_of[t]], "gap": src_of[t],
                      "category": "", "status": "candidate", "guard": None}
        added += 1
    vocab["terms"] = sorted(by_term.values(), key=lambda e: -e["freq"])
    vocab["updated"] = datetime.now().strftime("%Y-%m-%d")
    VOCAB.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"คลัง: +{added} candidate ใหม่ (รวม {len(vocab['terms'])})")

    rows = [["term", "freq", "gap", "ตัวอย่าง", "approve(✓/✗)", "หมวด", "guard"]]
    for e in vocab["terms"]:
        if e["status"] == "candidate":
            rows.append([e["term"], e["freq"], e["gap"], e["examples"][0], "", e["category"], e["guard"] or ""])
    gc = get_client()
    sh = gc.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet("vocab_review"); ws.clear()
    except Exception:
        ws = sh.add_worksheet(title="vocab_review", rows=len(rows) + 10, cols=7)
    ws.resize(rows=len(rows) + 2, cols=7)
    ws.update(values=rows, range_name="A1")
    ws.freeze(rows=1)
    print(f"📊 Sheet 'vocab_review': {len(rows)-1} candidate รอรีวิว")
    print("\n=== TOP 30 candidate ===")
    for e in vocab["terms"][:30]:
        if e["status"] == "candidate":
            print(f"  {e['freq']:>4}  [{e['gap']:>10}]  {e['term']}")


if __name__ == "__main__":
    main()
