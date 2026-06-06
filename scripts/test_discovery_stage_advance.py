"""test_discovery_stage_advance.py — ingest advance-stage UPSERT (B0→D0→W0) + stage_updated_at."""
import os, tempfile, sys
from pathlib import Path
os.environ["BMS_DATA_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import Sebastian_Customer_DB as db  # noqa: E402
db.init_schema()
import Sebastian_Province_Discovery as disc  # noqa: E402


def rec(pid, ann):
    return {"project_id": pid, "project_status": "", "announce_type": ann,
            "province": "นครพนม", "budget": 100, "project_name": "งานถนน",
            "dept_name": "อบต", "announce_date": "2026-06-01"}


def stage_of(pid):
    with db.get_connection() as c:
        return c.execute("SELECT announce_type, stage_updated_at FROM projects_seen WHERE project_id=?",
                         (pid,)).fetchone()


# new B0 → insert, stage_updated_at NULL
n, sk, adv = disc.ingest([rec("A", "B0")])
assert (n, sk, adv) == (1, 0, 0), (n, sk, adv)
row = stage_of("A"); assert row[0] == "B0" and row[1] is None, row

# B0 → D0 = advance (announce_type=D0, stage_updated_at set)
n, sk, adv = disc.ingest([rec("A", "D0")])
assert (n, sk, adv) == (0, 0, 1), (n, sk, adv)
row = stage_of("A"); assert row[0] == "D0" and row[1] is not None, row

# D0 → B0 = regress → ignore (คง D0)
n, sk, adv = disc.ingest([rec("A", "B0")])
assert (n, sk, adv) == (0, 1, 0), (n, sk, adv)
assert stage_of("A")[0] == "D0"

# D0 → W0 = advance
n, sk, adv = disc.ingest([rec("A", "W0")])
assert adv == 1 and stage_of("A")[0] == "W0", (adv, stage_of("A"))

print("✅ PASS discovery advance-stage UPSERT + stage_updated_at")
