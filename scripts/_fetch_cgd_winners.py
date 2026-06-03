"""Phase 2: ดึง winner ย้อนหลังจาก CGD egp-contract-2568 (นครพนม+บึงกาฬ),
filter awarded + construction keyword. quota-aware."""
import sys, json, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
import cgd_api_client as cg
import job_matcher as jm

cfg = jm.load_config()
KW = cfg.get("keywords", [])
PROVS = ["นครพนม", "บึงกาฬ"]
CALL_BUDGET = 350          # กัน quota 1000/วัน (เหลือ buffer)
PAGE = 1000

calls = 0
collected = {}             # รหัสโครงการ -> record
for prov in PROVS:
    prov_n = 0
    for rid in cg.EGP_CONTRACT_2568_RIDS:
        offset = 0
        while calls < CALL_BUDGET:
            res = cg._datastore_search(rid, filters={"จังหวัด": prov}, limit=PAGE, offset=offset)
            calls += 1
            if not res or not res.get("records"):
                break
            recs = res["records"]
            total = res.get("total", 0)
            for r in recs:
                winner = (r.get("ชื่อผู้ชนะ") or "").strip()
                name = (r.get("ชื่อโครงการ") or "")
                if winner and any(k in name for k in KW):
                    pid = str(r.get("รหัสโครงการ") or "").strip()
                    if pid and pid not in collected:
                        collected[pid] = r
                        prov_n += 1
            offset += PAGE
            if offset >= total:
                break
        if calls >= CALL_BUDGET:
            print(f"⚠️ ชน call budget {CALL_BUDGET} — หยุด (quota safety)")
            break
    print(f"{prov}: เก็บ {prov_n} (awarded+keyword) | calls สะสม {calls}")

json.dump(list(collected.values()), open("data/_cgd_winners_raw.json", "w", encoding="utf-8"),
          ensure_ascii=False)
print(f"\nรวม CGD awarded+keyword: {len(collected)} | total calls: {calls}")
