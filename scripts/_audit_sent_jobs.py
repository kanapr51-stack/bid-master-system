"""Audit: ทุกงานที่เคยเข้า notification_queue → รันกฎใหม่ (foreign-province + soft) หาเคสสกลนครเพิ่ม."""
import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "scripts")
import job_matcher as jm

DB = "/opt/bms/data/bms_customers.db"
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row
cfg = jm.load_config()
own = set(cfg.get("target_tambons", {}).keys())

rows = c.execute("""
  SELECT project_id,
         MAX(project_name_snapshot) AS name,
         MAX(province_snapshot) AS prov,
         MAX(source_stage) AS stage,
         SUM(status = 'sent') AS n_sent,
         COUNT(*) AS n
  FROM notification_queue
  GROUP BY project_id ORDER BY MIN(id)
""").fetchall()

print("distinct projects ที่เคยเข้า queue: %d\n" % len(rows))
header = "%-14s %4s %-22s %-9s | name" % ("project_id", "sent", "stage", "flag")
print(header)
sus = []
for r in rows:
    name = r["name"] or ""
    stage = r["stage"] or ""
    fp = jm.foreign_province_in_title(name, own)
    own_in = any(p in name for p in own)
    if fp and not own_in:
        flag = "FOREIGN"
        sus.append((r["project_id"], r["n_sent"], fp, name))
    elif stage == "province_soft_location":
        flag = "soft"
        sus.append((r["project_id"], r["n_sent"], "(soft)", name))
    else:
        flag = ""
    print("%-14s %4s %-22s %-9s | %s" % (r["project_id"], r["n_sent"], stage[:22], flag, name[:46]))

print("\n=== น่าสงสัย (foreign/soft) %d ===" % len(sus))
for pid, ns, fp, name in sus:
    # รันกฎใหม่ดูว่าตอนนี้จะตัดมั้ย
    dec = jm.match_job(name, "นครพนม", cfg=cfg)[0]
    print("  %s | sent=%s | foreign=%s | กฎใหม่→%s | %s" % (pid, ns, fp, dec, name[:50]))
