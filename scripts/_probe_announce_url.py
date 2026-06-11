"""_probe_announce_url.py — หา field ที่ใช้ทำลิงก์ประกาศจริง (seqNo/templateType/temp_Announ)
สำหรับงาน province_api. ดู 2 แหล่ง: infoProcureDocAnnounZip + getProjectDetail.

RSS ลิงก์จริง format: .../procsearch.sch?...&projectId=X&templateType=D2&temp_Announ=D&temp_itemNo=1&seqNo=N
→ ต้องรู้ templateType/temp_Announ/temp_itemNo/seqNo ต่องาน.

usage: python _probe_announce_url.py <project_id>
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8")
import process5_http_client as p
import requests

INFO_URL = "https://process5.gprocurement.go.th/egp-approval-service/apv-common/infoProcureDocAnnounZip"


def main():
    pid = sys.argv[1] if len(sys.argv) > 1 else "69059227331"
    print(f"=== probe announce fields: {pid} ===\n")

    # 1) infoProcureDocAnnounZip (ที่ DocZip ใช้หา templateId)
    token = p._get_token(pid)
    print(f"token: {'ok' if token else 'FAIL'}")
    try:
        h = p.HEADERS_NO_AUTH.copy(); h["X-Announcement-Token"] = token
        r = requests.get(INFO_URL, params={"projectId": pid}, headers=h, timeout=20)
        body = r.json()
        data = body.get("data") or {}
        print(f"\n[infoProcureDocAnnounZip] data keys: {list(data.keys())}")
        for k, v in data.items():
            vs = json.dumps(v, ensure_ascii=False)[:120]
            print(f"   {k} = {vs}")
    except Exception as e:
        print(f"[info] error: {e}")

    # 2) getProjectDetail (stepId/flowSeqno/announceType)
    try:
        d = p.get_project_detail(pid)
        print(f"\n[getProjectDetail]: {json.dumps(d, ensure_ascii=False)[:400]}")
    except Exception as e:
        print(f"[detail] error: {e}")


if __name__ == "__main__":
    main()
