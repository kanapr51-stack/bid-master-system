"""
probe_rss_semantics.py — RSS feed durability experiment

Runs at ~17:00 after suspected daytime outage to answer:
  Model A: feed is durable (latency-only outage)
  Model B: feed is transient (daytime D0s may be lost)

Evidence collected:
  1. pubDate distribution — are daytime items present? what shape?
  2. delta(pubDate → queued_at) — direct durability evidence
  3. availability confirmation

Usage:
  python scripts/probe_rss_semantics.py
"""
import sys
import io
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

TZ_TH = timezone(timedelta(hours=7))
NOW   = datetime.now(TZ_TH)

RSS_TARGETS = [
    ("0307", "https://process.gprocurement.go.th/egp2procmainWeb/rss/announcementList.rss?deptId=0307&anounceType=D0&lang=th"),
    ("0708", "https://process.gprocurement.go.th/egp2procmainWeb/rss/announcementList.rss?deptId=0708&anounceType=D0&lang=th"),
    ("8525", "https://process.gprocurement.go.th/egp2procmainWeb/rss/announcementList.rss?deptId=8525&anounceType=D0&lang=th"),
]

def fetch_rss(dept_id: str, url: str) -> dict:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BidMasterSystem/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read()
        latency = time.time() - t0
        root = ET.fromstring(body)
        items = root.findall(".//item")
        pub_dates = []
        for item in items:
            pd = item.findtext("pubDate") or ""
            title = item.findtext("title") or ""
            pub_dates.append({"pubDate": pd, "title": title[:60]})
        return {"ok": True, "latency": round(latency, 2), "items": pub_dates}
    except Exception as e:
        return {"ok": False, "latency": round(time.time()-t0, 2), "error": str(e)[:120]}


def parse_pubdate(s: str):
    """Parse RSS pubDate string -> datetime."""
    fmts = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s.strip(), fmt).astimezone(TZ_TH)
        except Exception:
            pass
    return None


def main():
    print(f"=== RSS Semantics Probe ===")
    print(f"Probe time: {NOW.strftime('%Y-%m-%d %H:%M')} ICT")
    print(f"Hypothesis: H_gov (RSS down 08:30-16:30 = government hours)")
    print()

    # Step 1: Check availability
    all_items = []
    for dept_id, url in RSS_TARGETS:
        result = fetch_rss(dept_id, url)
        status = "UP" if result["ok"] else "DOWN"
        print(f"  [{dept_id}] {status} latency={result['latency']}s", end="")
        if result["ok"]:
            print(f" items={len(result['items'])}")
            all_items.extend(result["items"])
        else:
            print(f" error={result.get('error','')[:60]}")

    if not any(fetch_rss(d, u)["ok"] for d, u in RSS_TARGETS[:1]):
        print("\nRSS still DOWN — H_gov recovery not yet confirmed")
        print("Try again in 30 min")
        return

    print(f"\nRSS is UP — {len(all_items)} total items fetched")

    # Step 2: pubDate distribution analysis
    print("\n--- pubDate distribution ---")
    today = NOW.date()
    daytime_start = NOW.replace(hour=8, minute=30, second=0, microsecond=0)
    daytime_end   = NOW.replace(hour=16, minute=30, second=0, microsecond=0)

    daytime_items = []
    evening_items = []
    other_items   = []
    unparseable   = 0

    for item in all_items:
        dt = parse_pubdate(item["pubDate"])
        if dt is None:
            unparseable += 1
            continue
        if dt.date() == today and daytime_start <= dt <= daytime_end:
            daytime_items.append((dt, item["title"]))
        elif dt.date() == today:
            evening_items.append((dt, item["title"]))
        else:
            other_items.append((dt, item["title"]))

    print(f"  Today daytime (08:30-16:30): {len(daytime_items)} items")
    print(f"  Today other times          : {len(evening_items)} items")
    print(f"  Other dates                : {len(other_items)} items")
    print(f"  Unparseable pubDate        : {unparseable}")

    if daytime_items:
        print("\n  Daytime items (pubDate distribution):")
        for dt, title in sorted(daytime_items):
            print(f"    {dt.strftime('%H:%M')}  {title[:55]}")

    # Step 3: delta(pubDate → queued_at) from existing rss_queue
    print("\n--- pubDate vs queued_at delta (from rss_queue) ---")
    try:
        queue = json.loads(Path("data/rss_queue.json").read_text(encoding="utf-8"))
        pub_map = {i["title"][:40]: i for i in queue if i.get("queued_at")}
        deltas = []
        for item in all_items:
            key = item["title"][:40]
            if key in pub_map:
                dt_pub = parse_pubdate(item["pubDate"])
                dt_q   = datetime.fromisoformat(pub_map[key]["queued_at"])
                if dt_pub and dt_q:
                    delta_min = (dt_q - dt_pub).total_seconds() / 60
                    deltas.append((delta_min, item["title"][:50]))

        if deltas:
            deltas.sort()
            print(f"  Matched {len(deltas)} items with existing queue")
            print(f"  delta min={deltas[0][0]:.0f}m  max={deltas[-1][0]:.0f}m  median={deltas[len(deltas)//2][0]:.0f}m")
            for delta_min, title in deltas[:5]:
                sign = "+" if delta_min >= 0 else ""
                print(f"    {sign}{delta_min:.0f}min  {title}")
        else:
            print("  No title matches found (new items not yet in queue)")
    except Exception as e:
        print(f"  Error reading rss_queue: {e}")

    # Step 4: Verdict
    print("\n--- Experiment verdict ---")
    if daytime_items:
        print("  RESULT: daytime items present → supports Model A (durable feed)")
        print("  H_gov corollary: downtime = latency gap only, not data loss")
        print("  Action: night-only harvesting strategy is SAFE")
    elif len(evening_items) > 0 and len(daytime_items) == 0:
        print("  RESULT: no daytime items — suspicious toward Model B or early batch publish")
        print("  Cannot conclude yet — need multi-day observation")
        print("  Action: consider adding 1 midday availability probe tomorrow")
    else:
        print("  RESULT: insufficient data — run again with more dept_ids")


if __name__ == "__main__":
    main()
