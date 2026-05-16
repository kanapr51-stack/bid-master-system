"""
scraper_metrics.py — Structured logging + anomaly detection for Scraper

Usage in Scraper:
    from scraper_metrics import ScraperMetrics
    m = ScraperMetrics()
    m.record_keyword("ตำบลโพนทอง", duration_ms=7300, items=10, new_items=0, ...)
    m.finalize(send_alerts=True)
"""
import json
import time
from pathlib import Path
from datetime import datetime, date
from collections import Counter
import sys
sys.stdout.reconfigure(encoding="utf-8")

METRICS_DIR = Path(__file__).parent.parent / "logs"
BASELINE_FILE = Path(__file__).parent.parent / "data" / "scrape_baseline.json"


class ScraperMetrics:
    """Collect per-keyword metrics, save JSON lines, detect anomalies"""

    def __init__(self):
        self.start_ts  = datetime.now()
        self.records   = []
        self.metrics_path = METRICS_DIR / f"scrape_metrics_{date.today().isoformat()}.jsonl"
        METRICS_DIR.mkdir(parents=True, exist_ok=True)

    def record_keyword(self, keyword: str, **fields):
        """fields: duration_ms, items, new_items, pages_fetched, status, rate_limited_pages, incremental_skip"""
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "keyword": keyword,
            **fields,
        }
        self.records.append(record)
        # Append to JSONL (incremental write — no data loss on crash)
        with self.metrics_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def total_duration_ms(self) -> int:
        return int((datetime.now() - self.start_ts).total_seconds() * 1000)

    def summary(self) -> dict:
        total_items = sum(r.get("items", 0) for r in self.records)
        total_new   = sum(r.get("new_items", 0) for r in self.records)
        total_pages = sum(r.get("pages_fetched", 0) for r in self.records)
        rate_lim    = sum(r.get("rate_limited_pages", 0) for r in self.records)
        skipped     = sum(1 for r in self.records if r.get("incremental_skip"))
        statuses    = Counter(r.get("status", "?") for r in self.records)
        return {
            "total_keywords":      len(self.records),
            "total_duration_ms":   self.total_duration_ms(),
            "total_duration_min":  self.total_duration_ms() / 60000,
            "total_items":         total_items,
            "total_new_items":     total_new,
            "total_pages_fetched": total_pages,
            "rate_limited_pages":  rate_lim,
            "incremental_skipped": skipped,
            "status_counts":       dict(statuses),
        }

    def detect_anomalies(self, baseline: dict = None) -> list:
        """Returns list of anomaly descriptions"""
        anomalies = []
        s = self.summary()

        # 1. Zero items across all keywords → likely schema break or full block
        if s["total_keywords"] >= 5 and s["total_items"] == 0:
            anomalies.append("🚨 ZERO ITEMS ALL KEYWORDS — schema break หรือ full block?")

        # 2. Rate limit > 30% of pages
        if s["total_pages_fetched"] > 0:
            rl_pct = s["rate_limited_pages"] / s["total_pages_fetched"] * 100
            if rl_pct > 30:
                anomalies.append(f"⚠️ Rate limited {rl_pct:.0f}% of pages — eGP cracking down?")

        # 3. Duration > 2x baseline
        if baseline and "avg_duration_min" in baseline:
            if s["total_duration_min"] > baseline["avg_duration_min"] * 2:
                anomalies.append(
                    f"⚠️ Duration {s['total_duration_min']:.1f}min vs baseline {baseline['avg_duration_min']:.1f}min (2x slower)"
                )

        # 4. High error status count
        err_count = s["status_counts"].get("error", 0) + s["status_counts"].get("failed", 0)
        if err_count > len(self.records) * 0.3:
            anomalies.append(f"⚠️ {err_count}/{len(self.records)} keywords errored")

        # 5. No incremental skip when expected (post-deploy regression)
        # Skip this for now — needs more context

        return anomalies

    def update_baseline(self):
        """Save rolling baseline (last 7 runs avg)"""
        if not BASELINE_FILE.exists():
            history = []
        else:
            try:
                history = json.loads(BASELINE_FILE.read_text(encoding="utf-8")).get("history", [])
            except Exception:
                history = []

        s = self.summary()
        history.append({
            "date":              date.today().isoformat(),
            "duration_min":      s["total_duration_min"],
            "total_items":       s["total_items"],
            "total_new_items":   s["total_new_items"],
            "incremental_skipped": s["incremental_skipped"],
        })
        # Keep last 14 runs
        history = history[-14:]
        avg_dur = sum(h["duration_min"] for h in history) / max(len(history), 1)

        BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_FILE.write_text(json.dumps({
            "updated":           datetime.now().isoformat(timespec="seconds"),
            "avg_duration_min":  avg_dur,
            "history":           history,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_baseline(self) -> dict:
        if not BASELINE_FILE.exists():
            return {}
        try:
            return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def finalize(self, send_discord: bool = True):
        """Compute summary + anomalies + alert Discord if needed"""
        s        = self.summary()
        baseline = self.load_baseline()
        anomalies = self.detect_anomalies(baseline)

        # Update baseline (after detect — so doesn't pollute)
        self.update_baseline()

        if send_discord:
            try:
                sys.path.insert(0, str(Path(__file__).parent))
                from Sebastian_Discord_Notify import load_env, get_credentials, send
                load_env()
                token, ch = get_credentials()
                lines = [
                    "📊 **Scraper Metrics**",
                    f"⏱️ {s['total_duration_min']:.1f} นาที | {s['total_keywords']} keywords | {s['total_items']} items ({s['total_new_items']} new)",
                    f"📄 {s['total_pages_fetched']} pages | ⚡ skipped {s['incremental_skipped']} (incremental)",
                ]
                if baseline.get("avg_duration_min"):
                    lines.append(f"📈 baseline: {baseline['avg_duration_min']:.1f} นาที")
                if anomalies:
                    lines.append("\n⚠️ **Anomalies:**")
                    for a in anomalies:
                        lines.append(f"  {a}")
                send(token, ch, "\n".join(lines))
            except Exception as e:
                print(f"Discord notify err: {e}", flush=True)

        return s, anomalies
