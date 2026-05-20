"""
Sebastian_Pipeline.py — Master runner รัน pipeline ทั้งหมด (local debug only)

NOTE: Automated pipeline รันบน GitHub Actions ไม่ต้องการ Chrome และไม่ต้องเปิดคอม
  - pipeline_daily.yml  → refresh + patch + classify + notify (ทุกวัน 06:00 ไทย)
  - rss_scraper.yml     → RSS discovery (ทุก :22 และ :52 UTC)

Usage:
    python Sebastian_Pipeline.py                  # รัน full pipeline
    python Sebastian_Pipeline.py --step download  # เฉพาะ doc download (ต้องการ Chrome)
    python Sebastian_Pipeline.py --step analyze   # parse + AI + merge → Sheet 2
    python Sebastian_Pipeline.py --step cost      # cost calculation → Sheet 3
    python Sebastian_Pipeline.py --step rank      # ranking → Sheet 4
    python Sebastian_Pipeline.py --step notify    # ส่งสรุปไป LINE + Discord
    python Sebastian_Pipeline.py --step snapshot  # extract metrics → snapshot.json
    python Sebastian_Pipeline.py --step deploy    # vercel deploy → dashboard live
    python Sebastian_Pipeline.py --no-deploy      # รัน full แต่ skip deploy step

Pipeline flow (local):
    rss → classify → refresh → download → analyze → cost → rank → notify → snapshot → deploy

Steps ที่ต้องการ Chrome (port 9222): download เท่านั้น
    Start-Process "chrome.exe" -ArgumentList "--remote-debugging-port=9222","--no-first-run","--user-data-dir=C:\\Temp\\ChromeDebug"
"""

import sys
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))

SCRIPTS_DIR  = Path(__file__).parent
DATA_DIR     = Path(__file__).parent.parent / "data"
DOWNLOAD_DIR = Path(__file__).parent.parent / "downloads"

# Discord notify — โหลดครั้งเดียว, ถ้าไม่มี token ก็ข้ามไป
try:
    from Sebastian_Discord_Notify import (
        load_env as _discord_load_env,
        get_credentials as _discord_creds,
        notify_pipeline_start,
        notify_step_done,
        notify_step_warn,
        notify_error,
        notify_pipeline_done,
        send as _discord_send,
    )
    _discord_load_env()
    try:
        _DISCORD_TOKEN, _DISCORD_CHANNEL = _discord_creds()
        _DISCORD_OK = True
        print("Discord: พร้อมส่งแจ้งเตือน", flush=True)
    except ValueError:
        _DISCORD_OK = False
        print("Discord: ไม่พบ token — ข้าม Discord notify", flush=True)
except ImportError:
    _DISCORD_OK = False


def _dc(fn, *args, **kwargs):
    """เรียก Discord function แบบ safe — ไม่ crash ถ้าไม่มี token"""
    if _DISCORD_OK:
        try:
            fn(_DISCORD_TOKEN, _DISCORD_CHANNEL, *args, **kwargs)
        except Exception as e:
            print(f"[WARN] Discord notify ผิดพลาด: {e}", flush=True)


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'='*60}", flush=True)
    print(f"[{ts}] PIPELINE: {msg}", flush=True)
    print(f"{'='*60}", flush=True)


def run_script(script_name: str) -> bool:
    """รัน Python script แล้วคืน True ถ้าสำเร็จ"""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        print(f"[ERROR] ไม่พบ script: {script_path}", flush=True)
        return False
    result = subprocess.run([sys.executable, str(script_path)], capture_output=False)
    return result.returncode == 0


def step_analyze():
    """
    Analyze step: PR45 Parser + TOR Analyzer + JSON Merger → Sheet 2 Writer
    วน loop บน download folders ทั้งหมด
    """
    import json

    # โหลด raw_jobs map จาก JSON backup ล่าสุด
    raw_job_files = sorted(DATA_DIR.glob("jobs_*.json"))
    if not raw_job_files:
        print("[ERROR] ไม่พบ jobs_*.json — รัน scraper ก่อน", flush=True)
        return False

    raw_jobs = json.loads(raw_job_files[-1].read_text(encoding="utf-8"))
    raw_job_map = {str(j.get("job_id", "")): j for j in raw_jobs}
    print(f"โหลด raw jobs: {len(raw_job_map)} งาน", flush=True)

    sys.path.insert(0, str(SCRIPTS_DIR))
    from Sebastian_PR45_Parser   import parse_job_docs
    from Sebastian_TOR_Analyzer  import analyze_job_tor
    from Sebastian_JSON_Merger   import merge_job_json
    from Sebastian_Sheet2_Writer import write_to_sheet2

    combined_all = []

    for job_id, raw_job in raw_job_map.items():
        job_dir = DOWNLOAD_DIR / job_id
        if not job_dir.exists():
            continue

        combined_path = job_dir / "combined.json"
        if combined_path.exists():
            combined_all.append(json.loads(combined_path.read_text(encoding="utf-8")))
            continue

        print(f"\n[analyze] {job_id}: {raw_job.get('title', '')[:50]}", flush=True)
        try:
            pr_results = parse_job_docs(job_dir)
            pr4 = pr_results.get("pr4", {})
            pr5 = pr_results.get("pr5", {})
            tor = analyze_job_tor(job_dir, raw_job)
            combined = merge_job_json(pr4, pr5, tor, raw_job)
            combined_path.write_text(
                json.dumps(combined, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            combined_all.append(combined)
            print(f"  W={combined.get('W')}, L={combined.get('L')}, T={combined.get('T')}, conf={combined.get('tor_confidence')}", flush=True)
        except Exception as e:
            print(f"  ERROR: {e}", flush=True)

    if combined_all:
        added = write_to_sheet2(combined_all)
        print(f"\nSheet 2: เพิ่ม {added} งาน", flush=True)

    return True


# ================================================================
# MAIN
# ================================================================

def main():
    parser = argparse.ArgumentParser(description="Sebastian Pipeline Runner")
    parser.add_argument(
        "--step",
        choices=["rss", "download", "classify", "refresh", "analyze", "cost", "rank", "notify", "snapshot", "deploy", "all"],
        default="all",
        help="step ที่จะรัน (default: all)",
    )
    parser.add_argument(
        "--no-deploy",
        action="store_true",
        help="skip dashboard deploy (มีประโยชน์ตอน dev — ประหยัด build time)",
    )
    args = parser.parse_args()
    step = args.step

    start = time.time()
    _dc(notify_pipeline_start)

    if step in ("all", "rss"):
        log("Step 1.5: RSS — discovery via RSS feed (cross-check process5)")
        ok = run_script("Sebastian_RSS_Scraper.py")
        if ok:
            _dc(notify_step_done, "rss", "RSS discovery รอบนี้สำเร็จ")
        else:
            print("[WARN] RSS discovery ไม่สำเร็จ (อาจไม่มี target_deptids.json)", flush=True)
            _dc(notify_step_warn, "rss", "RSS discovery ไม่สำเร็จ")

    if step in ("all", "download"):
        log("Step 2/8: DOWNLOAD — ดาวน์โหลด ปร.4, ปร.5, TOR")
        ok = run_script("Sebastian_Doc_Downloader.py")
        if ok:
            _dc(notify_step_done, "download", "ดาวน์โหลดเอกสารสำเร็จ")
        else:
            print("[WARN] Doc Downloader ไม่สำเร็จ", flush=True)
            _dc(notify_step_warn, "download", "Doc Downloader ไม่สำเร็จ")

    if step in ("all", "classify"):
        log("Step 3/8: CLASSIFY — จำแนก all_jobs → active/pending/awarded")
        ok = run_script("Sebastian_Classifier.py")
        if ok:
            _dc(notify_step_done, "classify", "จำแนกประเภทงานสำเร็จ")

    if step in ("all", "refresh"):
        log("Step 4/8: REFRESH — query eGP API สด → ตรวจ winner + status ของ active_bidding")
        # refresh_active_jobs.py จะ trigger Classifier rebuild ภายในหลัง update
        ok = run_script("refresh_active_jobs.py")
        if ok:
            _dc(notify_step_done, "refresh", "รีเฟรชสถานะ active_bidding สำเร็จ")
        else:
            print("[WARN] Refresh ไม่สำเร็จ", flush=True)
            _dc(notify_step_warn, "refresh", "รีเฟรช active_bidding ไม่สำเร็จ (HTTP-only — ตรวจสอบ network/rate limit)")

    if step in ("all", "analyze"):
        log("Step 5/8: ANALYZE — PR45 Parser + TOR AI + JSON Merge → Sheet 2")
        try:
            step_analyze()
            _dc(notify_step_done, "analyze", "วิเคราะห์เอกสาร PR45/TOR สำเร็จ")
        except Exception as e:
            _dc(notify_error, "analyze", str(e))
            raise

    if step in ("all", "cost"):
        log("Step 6/8: COST — เติม cost_data_By_Dexter → คำนวณต้นทุน")
        ok = run_script("Sebastian_Cost_Filler.py")
        if ok:
            _dc(notify_step_done, "cost", "คำนวณต้นทุนสำเร็จ")

    if step in ("all", "rank"):
        log("Step 7/8: RANK — จัดอันดับ → Sheet 4")
        ok = run_script("Sebastian_Ranker.py")
        if ok:
            _dc(notify_step_done, "rank", "จัดอันดับงานสำเร็จ")

    if step in ("all", "notify"):
        log("Step 8/10: NOTIFY — ส่งสรุปไป LINE + Discord")
        # LINE
        try:
            from Sebastian_LINE_Notify import notify_ranked_jobs as line_notify
            line_notify()
        except ValueError as e:
            print(f"[SKIP] LINE Notify: {e}", flush=True)
        except Exception as e:
            print(f"[WARN] LINE Notify ผิดพลาด: {e}", flush=True)
        # Discord
        try:
            from Sebastian_Discord_Notify import notify_ranked_jobs as discord_notify
            discord_notify()
        except ValueError as e:
            print(f"[SKIP] Discord Notify: {e}", flush=True)
        except Exception as e:
            print(f"[WARN] Discord Notify ผิดพลาด: {e}", flush=True)

    if step in ("all", "snapshot"):
        log("Step 9/10: SNAPSHOT — รวบรวม metrics → dashboard/web/public/snapshot.json")
        ok = run_script("dashboard_extractor.py")
        if ok:
            _dc(notify_step_done, "snapshot", "Snapshot dashboard สร้างสำเร็จ")
        else:
            print("[WARN] dashboard_extractor ไม่สำเร็จ", flush=True)
            _dc(notify_step_warn, "snapshot", "dashboard_extractor ไม่สำเร็จ — ดู log")

    if step in ("all", "deploy") and not args.no_deploy:
        log("Step 10/10: PUBLISH — upload snapshot ไป Vercel Blob → instant dashboard refresh")
        ok = run_script("Sebastian_Upload_Snapshot.py")
        if ok:
            _dc(notify_step_done, "publish", "Snapshot uploaded — dashboard อัปเดตทันที (< 5s)")
        else:
            # Fallback: ถ้า upload fail (Blob ล่ม) ก็ลอง full deploy
            print("[WARN] Upload fail — fallback to full deploy", flush=True)
            ok = run_script("Sebastian_Deploy_Dashboard.py")
            if ok:
                _dc(notify_step_done, "deploy", "Dashboard fully redeployed (fallback)")
            else:
                _dc(notify_step_warn, "publish", "Publish + deploy ทั้งคู่ fail — ตรวจ token/login")
    elif step in ("all",) and args.no_deploy:
        print("[INFO] ข้าม publish step (--no-deploy)", flush=True)

    elapsed = time.time() - start
    _dc(notify_pipeline_done, elapsed)
    print(f"\n{'='*60}", flush=True)
    print(f"Pipeline เสร็จสิ้นใน {elapsed:.1f} วินาที", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    main()
