"""bms_paths.py — Single Runtime-State Authority (P1 deploy-debt fix, 2026-06-01)

Invariant (ChatGPT + กัญจน์ + Claude converged):
  • repo (data/ ใน git)  = read-only assets เท่านั้น (config / lookup / seed / sample)
  • BMS_DATA_DIR         = ALL runtime writes (state ที่ mutate ระหว่างรัน)

ทำไม: เดิม scripts ปนกัน — บางตัว Path(__file__).parent.parent/"data" (เขียน tracked dir)
บางตัว BMS_DATA_DIR → 2 write path = git conflict ทุก deploy + เสี่ยง split-brain
(reader อ่าน dir นึง / writer เขียนอีก dir). helper นี้บังคับ runtime write ที่เดียว.

ดู: progress_log.md งานที่ N+5x (P1 deploy-debt), memory/project_deploy_debt

⚠️ STATUS 2026-06-01: DORMANT INFRASTRUCTURE — reserved for future canonical path migration.
ยังไม่มี caller (full migration step 2-9 = DEFERRED, ดู tripwires ใน memory/project_deploy_debt).
interim fix (Windows หยุด push data) แก้ deploy conflict แล้ว → ไม่จำเป็นเร่ง. ห้ามถอน
(tested + fail-loud + no caller = near-zero risk; "สะพานที่สร้างไว้แต่ยังไม่เปิดจราจร").
"""
import os
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_runtime_dir() -> Path:
    """resolve BMS_DATA_DIR — fail loud ถ้าไม่ตั้ง (กัน split-brain จาก fallback เงียบ).
    dev escape hatch: ต้องตั้งใจ BMS_ENV=dev เท่านั้น → ./data/runtime (gitignored)."""
    env = os.environ.get("BMS_DATA_DIR")
    if env:
        return Path(env).resolve()
    if os.environ.get("BMS_ENV") == "dev":
        p = (_REPO_ROOT / "data" / "runtime").resolve()
        p.mkdir(parents=True, exist_ok=True)
        print(f"[bms_paths] WARN: BMS_DATA_DIR ไม่ตั้ง — dev fallback {p}", file=sys.stderr)
        return p
    raise RuntimeError(
        "BMS_DATA_DIR ไม่ได้ตั้ง — runtime state ต้องมี dir ชัดเจน (กัน split-brain). "
        "ตั้ง env BMS_DATA_DIR=/opt/bms/data หรือ BMS_ENV=dev สำหรับ local dev")


RUNTIME_DIR = _resolve_runtime_dir()


def runtime_path(name: str) -> Path:
    """path ของ runtime-state file ใต้ BMS_DATA_DIR (single write authority).
    guard: ต้องอยู่ใต้ RUNTIME_DIR เสมอ (กัน path escape → split-brain)."""
    p = (RUNTIME_DIR / name).resolve()
    if not str(p).startswith(str(RUNTIME_DIR)):
        raise ValueError(f"runtime path escape: {p} ไม่อยู่ใต้ {RUNTIME_DIR}")
    return p


def asset_path(name: str) -> Path:
    """path ของ read-only asset (config / seed / lookup) ใน repo — ห้ามเขียน runtime ที่นี่."""
    return (_REPO_ROOT / "data" / name).resolve()


def heal_legacy_state(*names: str) -> list:
    """dual-read transition (time-boxed, ถอด Phase 4): ถ้า runtime file หายแต่ legacy app/data มี
    → copy + LOG ดังๆ (= copy migration พลาด, ต้องสืบ). คืน list ที่ heal. ไม่ทับ runtime ที่มีอยู่."""
    healed = []
    for name in names:
        new = runtime_path(name)
        if new.exists():
            continue
        old = (_REPO_ROOT / "data" / name)
        if old.exists():
            shutil.copy2(old, new)
            print(f"[bms_paths] ⚠️ DUAL-READ HEAL: {name} หายใน {RUNTIME_DIR} → copy จาก {old} "
                  f"(migration copy พลาด? ต้องสืบ)", file=sys.stderr)
            healed.append(name)
    return healed


def log_paths(*names: str) -> None:
    """startup instrumentation (Q2.5) — log resolved runtime path เพื่อ verify
    ว่าทุก process ใช้ dir เดียวกันจริง. ถ้า log ยังเห็น app/data = มี writer/reader หลุด."""
    print(f"[bms_paths] RUNTIME_DIR={RUNTIME_DIR}", file=sys.stderr)
    for n in names:
        print(f"[bms_paths]   {n} -> {runtime_path(n)}", file=sys.stderr)
