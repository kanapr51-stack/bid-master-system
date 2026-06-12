#!/usr/bin/env bash
# ตรวจว่างานหนึ่งคาดราคาได้ไหม + ทำไม (resolve/คู่แข่ง). รันบน VPS:
#   bash scripts/verify_job.sh 69069138608
PID="${1:?ใส่ project_id เช่น: bash scripts/verify_job.sh 69069138608}"
cd /opt/bms/app
BMS_DATA_DIR=/opt/bms/data /opt/bms/venv/bin/python -c "
import sys; sys.path.insert(0,'scripts'); sys.stdout.reconfigure(encoding='utf-8')
import cgd_intel as ci
from collections import Counter
from Sebastian_Customer_DB import get_connection
pid='$PID'; conn=get_connection(); conn.row_factory=__import__('sqlite3').Row
r=conn.execute('SELECT project_name,province,dept_name,budget FROM projects_seen WHERE project_id=?',(pid,)).fetchone()
if not r:
    print('ไม่พบงาน', pid); sys.exit()
print('งาน:', r['project_name'][:55])
print('จว:', r['province'], '| งบ:', r['budget'])
print('keywords:', ci.match_keywords(r['project_name']))
loc=ci.resolve_location(pid,r['project_name'],r['dept_name'] or '',r['province'],conn)
print('resolve:', loc['tambon'], loc['amphoe'], '| src', loc['source'])
print('trace:', loc['resolution_trace'])
ctx=ci.intel_context(r['province'],r['project_name'],r['dept_name'] or '',pid,r['budget'] or 0)
print('ผลคาดราคา:', 'มีราคาคาด ✅' if ctx and ctx.get('prediction') else 'None = คาดไม่ได้')
rows=ci._fetch(conn,r['province'],ci.match_keywords(r['project_name']))
print('คู่แข่ง by district:', dict(Counter(x.get('district') for x in rows)))
"
