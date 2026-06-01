"""probe_rate_limit.py — Phase 0: หา rate limit จริงของ getProcurementDetail (2026-06-02)

วัด: (1) ชนที่ call ที่เท่าไหร่ + กี่วินาที (2) scope per-IP vs per-token
     (3) recovery/reset time หลังชน

⚠️ ยิงรัวจนชน rate limit → trigger cooldown กระทบ production resolve ชั่วคราว
   ควรรันตอน traffic ต่ำ (ดึก) — discovery รอบถัดไป 07:00

Usage: python scripts/probe_rate_limit.py [--max 250]
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import requests
import process5_http_client as p

URL = ("https://process5.gprocurement.go.th/egp-atpj27-service/"
       "pb/a-egp-allt-project/announcement/getProcurementDetail")


def is_rate(r) -> bool:
    return r.status_code == 429 or ("rate limit" in r.text.lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=250, help="ยิงสูงสุดกี่ call")
    ap.add_argument("--db", default="/opt/bms/data/bms_customers.db")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    pids = [row[0] for row in conn.execute(
        "SELECT project_id FROM projects_seen WHERE source='province_api' LIMIT ?",
        (args.max + 10,),
    )]
    conn.close()
    if len(pids) < 10:
        print(f"❌ project ไม่พอ probe (มี {len(pids)}) — ต้อง >= 10")
        return

    print(f"=== Phase 0 probe getProcurementDetail — ยิงสูงสุด {args.max} project (token ต่างกัน) ===")
    print(f"projects available: {len(pids)}")
    print("ยิงรัว (ไม่ sleep) จนกว่าจะชน...\n")

    t0 = time.time()
    n_ok = 0
    token_fail = 0
    hit = None
    latencies = []

    for i, pid in enumerate(pids[:args.max], 1):
        try:
            tok = p._get_token(pid)              # AES generateToken (per-project)
            if not tok:
                token_fail += 1
                if token_fail <= 3 or token_fail % 10 == 0:
                    print(f"  call {i}: ⚠️ generateToken ว่าง (token_fail={token_fail})")
                continue
            h = p.HEADERS_NO_AUTH.copy()
            h["X-Announcement-Token"] = tok
            r = requests.get(URL, params={"projectId": pid}, headers=h, timeout=15)
            el = time.time() - t0
            latencies.append(r.elapsed.total_seconds() * 1000)
            if is_rate(r):
                hit = (i, el, r.status_code)
                print(f"\n🔴 ชนที่ call #{i} | elapsed {el:.1f}s | "
                      f"http={r.status_code} | สำเร็จก่อนชน {n_ok} calls")
                break
            n_ok += 1
            if i % 25 == 0:
                rate = n_ok / el if el > 0 else 0
                print(f"  call {i}: ok | elapsed {el:.1f}s | rate {rate:.1f}/s | "
                      f"latency~{sum(latencies)/len(latencies):.0f}ms")
        except requests.Timeout:
            print(f"  call {i}: timeout")
        except Exception as e:
            print(f"  call {i}: ERR {type(e).__name__}: {e}")

    print("\n=== สรุป threshold ===")
    if not hit:
        el = time.time() - t0
        print(f"✅ ไม่ชนใน {n_ok} calls / {el:.1f}s (rate {n_ok/el:.1f}/s) | token_fail={token_fail}")
        print("   → limit สูงกว่าที่ทดสอบ หรือ per-token (token ต่างกัน budget แยก)")
        return
    print(f"ชนที่ call #{hit[0]} | {hit[1]:.1f}s | สำเร็จก่อนชน {n_ok}")
    print(f"scope: ยิงด้วย token คนละตัว (per-project) แล้วยังชน → น่าจะ **per-IP** "
          f"(ถ้า per-token จะไม่ชนเพราะ budget แยก)")

    # วัด recovery/reset
    print("\n=== วัด recovery (poll 1 call ทุก 20s, สูงสุด 180s) ===")
    rec0 = time.time()
    recovered = False
    while time.time() - rec0 < 180:
        time.sleep(20)
        try:
            tok = p._get_token(pids[0])
            h = p.HEADERS_NO_AUTH.copy()
            h["X-Announcement-Token"] = tok
            r = requests.get(URL, params={"projectId": pids[0]}, headers=h, timeout=15)
            waited = time.time() - rec0
            if not is_rate(r):
                print(f"✅ กลับมาได้หลัง ~{waited:.0f}s (จากตอนชน) → reset window ≈ {waited:.0f}s")
                recovered = True
                break
            print(f"  +{waited:.0f}s: ยังชนอยู่")
        except Exception as e:
            print(f"  poll ERR {type(e).__name__}")
    if not recovered:
        print("⚠️ ยังไม่กลับใน 180s — window ยาวกว่า 3 นาที หรือ block หนัก")


if __name__ == "__main__":
    main()
