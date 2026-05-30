"""
deadline_service.py — Deadline Resolution Plane (authoritative bid deadline)

Architecture (ChatGPT + Claude converged 2026-05-30):
- IDeadlineProvider abstraction → สลับแหล่ง deadline โดยไม่แตะ Qualification Worker
  (มิเรอร์ ITokenProvider ใน token_service.py)
- NullDeadlineProvider = default → resolve ไม่ได้ → fail-closed (beta เงียบอย่างปลอดภัย)
- เมื่อ resolver จริงพร้อม (GreenBook→PDF) ก็แค่สลับ provider

Invariant: "Authoritative Deadline Gate ก่อน Notification Queue" — ทุก source ผ่าน gate นี้
หลัก: ปัญหาคือ "finding the PDF" ไม่ใช่ "extract deadline" → reuse parser ที่ proven (patch_deadlines)

Provider roadmap:
  NullDeadlineProvider       = default (fail-closed) — deploy ได้เลย
  GreenBookDeadlineProvider  = Tier A (greenBook → templateId → PDF → pdfplumber)  [RE อยู่]
  CDPClickThroughProvider    = Tier B emergency fallback (UI fragility)
"""
import os
import sys
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from datetime import date, datetime
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8")


def _data_dir() -> str:
    return os.environ.get("BMS_DATA_DIR",
                          os.path.join(os.path.dirname(__file__), "..", "data"))


def _now() -> float:
    return time.time()


# ── Result / state ──────────────────────────────────────────────────────────────

class DeadlineOutcome(Enum):
    RESOLVED = "resolved"        # ได้ deadline จริง
    NO_DOCUMENT = "no_document"  # หา document linkage ไม่ได้ (greenBook ว่าง)
    PARSE_FAILED = "parse_failed"  # ได้ PDF แต่ parse deadline ไม่ได้
    PROVIDER_ERROR = "provider_error"  # provider ล้มเหลว (network/WAF/timeout)
    NOT_APPLICABLE = "not_applicable"  # Null provider / ไม่รองรับ


@dataclass
class DeadlineResult:
    project_id: str
    outcome: DeadlineOutcome
    deadline: Optional[date] = None       # วันยื่นข้อเสนอ (authoritative)
    provider: str = ""
    latency_ms: int = 0
    source_doc: Optional[str] = None      # templateId / pdfUrl ที่ใช้
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.outcome == DeadlineOutcome.RESOLVED and self.deadline is not None

    def is_open(self, today: Optional[date] = None) -> bool:
        """deadline >= today (ยังเปิดยื่นซอง)"""
        if not self.success:
            return False
        return self.deadline >= (today or date.today())


# ── Provider interface ──────────────────────────────────────────────────────────

class IDeadlineProvider:
    name = "base"

    def resolve(self, project_id: str, **ctx) -> DeadlineResult:
        raise NotImplementedError


class NullDeadlineProvider(IDeadlineProvider):
    """default — resolve ไม่ได้เสมอ → qualification fail-closed (beta เงียบอย่างปลอดภัย)
    ใช้ deploy pipeline ก่อน resolver จริงพร้อม"""
    name = "null"

    def resolve(self, project_id: str, **ctx) -> DeadlineResult:
        return DeadlineResult(project_id, DeadlineOutcome.NOT_APPLICABLE,
                              provider=self.name,
                              error="no deadline provider configured (fail-closed)")


# ── Deadline Service (provider orchestration + telemetry) ───────────────────────

class DeadlineService:
    def __init__(self, provider: IDeadlineProvider, telemetry_path: str = ""):
        self.provider = provider
        self.telemetry_path = telemetry_path or os.path.join(
            _data_dir(), "deadline_resolution_log.ndjson")

    def _record(self, res: DeadlineResult):
        rec = {
            "ts": _now(),
            "project_id": res.project_id,
            "provider": res.provider,
            "outcome": res.outcome.value,
            "success": res.success,
            "deadline": res.deadline.isoformat() if res.deadline else None,
            "latency_ms": res.latency_ms,
            "source_doc": res.source_doc,
            "error": res.error,
        }
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.telemetry_path)), exist_ok=True)
            with open(self.telemetry_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def resolve(self, project_id: str, **ctx) -> DeadlineResult:
        t0 = _now()
        try:
            res = self.provider.resolve(project_id, **ctx)
        except Exception as e:
            res = DeadlineResult(project_id, DeadlineOutcome.PROVIDER_ERROR,
                                 provider=self.provider.name,
                                 error=f"{type(e).__name__}: {e}")
        if not res.latency_ms:
            res.latency_ms = int((_now() - t0) * 1000)
        self._record(res)
        return res


# ── factory ─────────────────────────────────────────────────────────────────────

def make_deadline_provider(name: str = "") -> IDeadlineProvider:
    name = name or os.environ.get("BMS_DEADLINE_PROVIDER", "null")
    # GreenBook/CDP providers จะ register ที่นี่เมื่อพร้อม
    if name == "greenbook":
        try:
            from deadline_provider_greenbook import GreenBookDeadlineProvider
            return GreenBookDeadlineProvider()
        except Exception:
            pass
    return NullDeadlineProvider()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="null")
    ap.add_argument("--project", default="TEST123")
    a = ap.parse_args()
    svc = DeadlineService(make_deadline_provider(a.provider))
    r = svc.resolve(a.project)
    print(json.dumps({
        "project_id": r.project_id, "outcome": r.outcome.value,
        "success": r.success, "deadline": r.deadline.isoformat() if r.deadline else None,
        "provider": r.provider, "error": r.error,
    }, ensure_ascii=False, indent=2))
