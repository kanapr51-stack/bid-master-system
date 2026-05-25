"""
Sebastian_Heatmap.py — BMS RSS availability heatmap generator

Queries bms_telemetry.db and generates 4-panel PNG:
  Panel 1: Availability by hour-of-day (success rate %)
  Panel 2: Response time by hour (avg ms — v2 full_metrics only)
  Panel 3: Failure reason distribution (stacked bar)
  Panel 4: Items discovered by hour

Output: reports/rss_health_YYYY-MM-DD.png

Usage:
  python scripts/Sebastian_Heatmap.py
  python scripts/Sebastian_Heatmap.py --days 14
  python scripts/Sebastian_Heatmap.py --out reports/custom.png
"""
import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive — safe on GHA / no display
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

DB_PATH  = Path(__file__).parent.parent / "data" / "bms_telemetry.db"
RPT_DIR  = Path(__file__).parent.parent / "reports"

FAILURE_COLORS = {
    "timeout":          "#e74c3c",
    "connection_error": "#c0392b",
    "tls_error":        "#8e44ad",
    "http_429":         "#e67e22",
    "http_503":         "#d35400",
    "empty_response":   "#7f8c8d",
    "unknown_error":    "#95a5a6",
}


# ──────────────────────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────────────────────

def _connect():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def load_rows(days: int) -> list[sqlite3.Row]:
    """Load poll_log rows from the last N days."""
    if not DB_PATH.exists():
        print(f"[heatmap] DB not found: {DB_PATH}", file=sys.stderr)
        return []
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM poll_log WHERE polled_at >= ? ORDER BY polled_at ASC",
        (cutoff,)
    ).fetchall()
    conn.close()
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# Aggregation helpers
# ──────────────────────────────────────────────────────────────────────────────

def agg_by_hour(rows: list) -> dict:
    """Returns per-hour aggregates (0–23)."""
    buckets = {h: {"ok": 0, "fail": 0, "rt_sum": 0.0, "rt_n": 0,
                   "items": 0, "reasons": defaultdict(int)}
               for h in range(24)}
    for r in rows:
        try:
            h = datetime.fromisoformat(r["polled_at"]).hour
        except (ValueError, TypeError):
            continue
        b = buckets[h]
        if r["success"]:
            b["ok"] += 1
        else:
            b["fail"] += 1
            reason = r["failure_reason"] or "unknown_error"
            b["reasons"][reason] += 1
        if r["response_time_ms"] is not None:
            b["rt_sum"] += r["response_time_ms"]
            b["rt_n"]   += 1
        b["items"] += r["items_count"] or 0
    return buckets


def agg_by_day_hour(rows: list) -> tuple[list, np.ndarray]:
    """Returns (day_labels, 7×24 matrix of success rates). Rows = days, cols = hours."""
    by_day: dict[str, dict] = defaultdict(lambda: {h: {"ok": 0, "fail": 0} for h in range(24)})
    for r in rows:
        try:
            dt = datetime.fromisoformat(r["polled_at"])
        except (ValueError, TypeError):
            continue
        day = dt.strftime("%Y-%m-%d")
        if r["success"]:
            by_day[day][dt.hour]["ok"] += 1
        else:
            by_day[day][dt.hour]["fail"] += 1

    if not by_day:
        return [], np.full((1, 24), np.nan)

    days = sorted(by_day.keys())
    matrix = np.full((len(days), 24), np.nan)
    for i, day in enumerate(days):
        for h in range(24):
            b = by_day[day][h]
            total = b["ok"] + b["fail"]
            if total > 0:
                matrix[i, h] = b["ok"] / total * 100
    return days, matrix


# ──────────────────────────────────────────────────────────────────────────────
# Panels
# ──────────────────────────────────────────────────────────────────────────────

def _panel_availability_heatmap(ax, days: list, matrix: np.ndarray, title: str):
    """Day x hour heatmap — NaN = no data (grey)."""
    cmap = plt.cm.RdYlGn.copy()
    cmap.set_bad(color="#eeeeee")

    masked = np.ma.masked_where(np.isnan(matrix), matrix)
    im = ax.imshow(masked, cmap=cmap, vmin=0, vmax=100,
                   aspect="auto", interpolation="none")

    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7)
    ax.set_yticks(range(len(days)))
    ax.set_yticklabels(days, fontsize=7)
    ax.set_xlabel("Hour (Thai time)", fontsize=8)
    ax.set_title(title, fontsize=9, fontweight="bold")

    # Annotate cells that have data
    for i in range(len(days)):
        for h in range(24):
            if not np.isnan(matrix[i, h]):
                ax.text(h, i, f"{matrix[i,h]:.0f}",
                        ha="center", va="center", fontsize=6,
                        color="white" if matrix[i, h] < 50 else "black")

    plt.colorbar(im, ax=ax, label="Success %", fraction=0.02, pad=0.02)


def _panel_hourly_bars(ax, buckets: dict, title: str):
    """24-bar availability chart with success rate %."""
    hours = list(range(24))
    success_rates = []
    totals = []
    for h in hours:
        b   = buckets[h]
        tot = b["ok"] + b["fail"]
        sr  = b["ok"] / tot * 100 if tot else np.nan
        success_rates.append(sr)
        totals.append(tot)

    colors = []
    for sr in success_rates:
        if np.isnan(sr):
            colors.append("#dddddd")
        elif sr >= 80:
            colors.append("#27ae60")
        elif sr >= 40:
            colors.append("#f39c12")
        else:
            colors.append("#e74c3c")

    valid = [sr for sr in success_rates if not np.isnan(sr)]
    bars = ax.bar(hours, [sr if not np.isnan(sr) else 0 for sr in success_rates],
                  color=colors, width=0.8, edgecolor="white", linewidth=0.5)

    # Sample count annotation
    for h, tot in enumerate(totals):
        if tot > 0:
            ax.text(h, 2, f"n={tot}", ha="center", va="bottom",
                    fontsize=5.5, color="#555555", rotation=90)

    ax.set_xlim(-0.5, 23.5)
    ax.set_ylim(0, 110)
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}" for h in hours], fontsize=7)
    ax.set_ylabel("Success rate (%)", fontsize=8)
    ax.set_xlabel("Hour (Thai time, UTC+7)", fontsize=8)
    ax.set_title(title, fontsize=9, fontweight="bold")
    ax.axhline(80, color="#27ae60", linestyle="--", linewidth=0.8, alpha=0.6, label="80% target")
    ax.legend(fontsize=7)
    ax.yaxis.grid(True, linestyle=":", alpha=0.4)

    # Overall availability annotation
    if valid:
        overall = np.nanmean(success_rates)
        ax.text(23.4, 105, f"Overall: {overall:.0f}%",
                ha="right", va="top", fontsize=8, color="#2c3e50",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#ecf0f1", alpha=0.8))


def _panel_response_time(ax, buckets: dict, title: str):
    """Avg response time by hour (only for rows with full_metrics)."""
    hours = list(range(24))
    avgs  = []
    for h in hours:
        b = buckets[h]
        avg = b["rt_sum"] / b["rt_n"] if b["rt_n"] > 0 else np.nan
        avgs.append(avg / 1000 if not np.isnan(avg) else np.nan)  # ms → s

    valid_h   = [h for h, v in zip(hours, avgs) if not np.isnan(v)]
    valid_v   = [v for v in avgs if not np.isnan(v)]

    if valid_h:
        ax.plot(valid_h, valid_v, "o-", color="#3498db", linewidth=1.5,
                markersize=5, label="Avg response time")
        ax.fill_between(valid_h, valid_v, alpha=0.15, color="#3498db")
        # Highlight high-latency hours (> 5s = near timeout)
        for h, v in zip(valid_h, valid_v):
            if v > 5:
                ax.annotate(f"{v:.1f}s", (h, v), textcoords="offset points",
                            xytext=(0, 6), ha="center", fontsize=6.5, color="#e74c3c")
    else:
        ax.text(12, 0.5, "No response time data yet\n(accumulates with live polls)",
                ha="center", va="center", fontsize=9, color="#7f8c8d",
                transform=ax.transAxes)

    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}" for h in hours], fontsize=7)
    ax.set_ylabel("Response time (s)", fontsize=8)
    ax.set_xlabel("Hour (Thai time)", fontsize=8)
    ax.set_title(title, fontsize=9, fontweight="bold")
    ax.axhline(8, color="#e74c3c", linestyle="--", linewidth=0.8,
               alpha=0.6, label="Timeout threshold (8s)")
    ax.axhline(3, color="#f39c12", linestyle=":", linewidth=0.8,
               alpha=0.6, label="Slow threshold (3s)")
    ax.legend(fontsize=7)
    ax.yaxis.grid(True, linestyle=":", alpha=0.4)


def _panel_failure_reasons(ax, buckets: dict, title: str):
    """Stacked bar: failure reasons by hour."""
    hours = list(range(24))
    reason_keys = sorted(
        set(r for b in buckets.values() for r in b["reasons"].keys()),
        key=lambda r: -sum(buckets[h]["reasons"].get(r, 0) for h in hours)
    )

    if not reason_keys:
        ax.text(0.5, 0.5, "No failures recorded yet",
                ha="center", va="center", fontsize=9, color="#27ae60",
                transform=ax.transAxes)
        ax.set_title(title, fontsize=9, fontweight="bold")
        return

    bottom = np.zeros(24)
    for reason in reason_keys:
        vals   = [buckets[h]["reasons"].get(reason, 0) for h in hours]
        color  = FAILURE_COLORS.get(reason, "#bdc3c7")
        ax.bar(hours, vals, bottom=bottom, label=reason, color=color,
               width=0.8, edgecolor="white", linewidth=0.4)
        bottom += np.array(vals, dtype=float)

    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}" for h in hours], fontsize=7)
    ax.set_ylabel("Failure count", fontsize=8)
    ax.set_xlabel("Hour (Thai time)", fontsize=8)
    ax.set_title(title, fontsize=9, fontweight="bold")
    ax.legend(fontsize=7, loc="upper right")
    ax.yaxis.grid(True, linestyle=":", alpha=0.4)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def generate(days: int = 30, out_path: Path | None = None) -> Path:
    rows = load_rows(days)
    total = len(rows)
    print(f"[heatmap] {total} poll_log rows (last {days} days)")

    buckets            = agg_by_hour(rows)
    day_labels, matrix = agg_by_day_hour(rows)

    RPT_DIR.mkdir(exist_ok=True)
    if out_path is None:
        today    = datetime.now().strftime("%Y-%m-%d")
        out_path = RPT_DIR / f"rss_health_{today}.png"

    # ── 4-panel vertical layout (portrait) ───────────────────────────────────
    n_days    = max(len(day_labels), 1)
    hmap_h    = max(2.0, n_days * 0.4)     # heatmap height scales with day count
    fig_h     = 7.5 + hmap_h               # top 3 panels + heatmap
    fig, axes = plt.subplots(
        4, 1,
        figsize=(16, fig_h),
        gridspec_kw={"height_ratios": [2.5, 2.2, 2.2, hmap_h],
                     "hspace": 0.55},
    )
    fig.patch.set_facecolor("#f8f9fa")

    _panel_hourly_bars(
        axes[0], buckets,
        f"Panel 1: Availability by Hour  [n={total} polls]",
    )
    _panel_response_time(
        axes[1], buckets,
        "Panel 2: Response Time by Hour",
    )
    _panel_failure_reasons(
        axes[2], buckets,
        "Panel 3: Failure Reason by Hour",
    )
    if len(day_labels) >= 1:
        _panel_availability_heatmap(
            axes[3], day_labels, matrix,
            f"Panel 4: Availability Heatmap (day × hour)  [grey = no data]",
        )
    else:
        axes[3].text(0.5, 0.5, "Accumulating data...",
                     ha="center", va="center", fontsize=10, color="#7f8c8d",
                     transform=axes[3].transAxes)
        axes[3].set_title("Panel 4: Availability Heatmap", fontsize=9, fontweight="bold")

    # ── Title ─────────────────────────────────────────────────────────────────
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    fig.suptitle(
        f"BMS — eGP RSS Health Report  |  Last {days} days  |  Generated {generated_at}",
        fontsize=12, fontweight="bold", color="#2c3e50",
    )

    fig.savefig(str(out_path), dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"[heatmap] Saved: {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BMS RSS availability heatmap")
    parser.add_argument("--days", type=int, default=30, help="Look-back window in days")
    parser.add_argument("--out", type=str, default=None, help="Output PNG path")
    args = parser.parse_args()

    out = generate(
        days=args.days,
        out_path=Path(args.out) if args.out else None,
    )
    print(f"Done: {out}")
