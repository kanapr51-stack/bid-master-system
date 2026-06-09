# สรุปข้อมูลการเสนอราคาเบื้องต้น — API chain (RE 2026-06-09)

**เป้าหมาย:** ดึง "ราคาต่ำสุดที่เสนอ" (early signal) ทันทีหลังประมูลจบ — เร็วกว่า `getProcureResult` (ผลทางการ priceAgree) เป็นวันๆ. ใช้ทำ W0 **Round 1 (แจ้งเบื้องต้น)** ของ feature แจ้ง 2 รอบ (กัญจน์เลือก Option C 2026-06-09).

**Context:** งาน 69059075454 — getProcureResult ยัง resultFlag='N' (ว่าง) + getProjectDetail ยัง "กำลังประมูล" แต่ "สรุปข้อมูลการเสนอราคาเบื้องต้น" เปิดเผยแล้ว 12:02 (ราคาต่ำสุด 740,000). RE ผ่าน playwright capture (Chrome 9222) หน้า `egp-agpc01-web/announcement/procurement/<token>`.

## URL หน้าเว็บ (web)
```
https://process5.gprocurement.go.th/egp-agpc01-web/announcement/procurement/<TOKEN>
TOKEN = process5_http_client._encrypt_data({"projectId": pid})   # CryptoJS Salted, passphrase RDCrypto (ชั้นเดียว)
```

## Pure-API chain (พิสูจน์ end-to-end บน VPS — ไม่ต้อง browser)
ทุก call แนบ `X-Announcement-Token` = `p._get_token(pid)` (AES token เดิม). คงที่:
```
PASSKEY     = "0b3464ada27f4a3baaf863dc3e68f8b9"
APIKEY_UUID = "0b3464ad-a27f-4a3b-aaf8-63dc3e68f8b9"   # = passKey จัดรูป UUID
```

1. **encryptApiKey** (server-side encrypt — atpj27 service เดิม):
   ```
   GET {API_BASE}/encryptApiKey?passKey=<PASSKEY>&sDataValue=<projectId>   → data = enc_projectId
   GET {API_BASE}/encryptApiKey?passKey=<PASSKEY>&sDataValue=<APIKEY_UUID> → data = enc_apiKey
   ```
   (API_BASE = egp-atpj27-service/pb/a-egp-allt-project/announcement)

2. **genReportPrice** (สร้าง report PDF — service ใหม่):
   ```
   GET egp-merchant-ebidding-service/common/genReportPrice?projectId=<enc_projectId>&apiKey=<enc_apiKey>
       → data = report templateId (UUID)
   ```

3. **viewPdf** (ดึง PDF base64):
   ```
   POST egp-template-service/FileViewer/viewPdf/<UUID>   body {}   → data = base64(PDF)
   ```

4. **parse** (pdfplumber, Thai digits ๐-๙ → 0-9):
   - `จำนวนผู้เสนอราคา : N ราย`
   - `รายการพิจารณาที่ X ... <ราคาต่ำสุดที่เสนอ>` (เช่น 740,000.00)
   - `เปิดเผย ณ วันที่ ... เวลา HH:MM น.` (published timestamp)
   - `เวลาสิ้นสุดการเสนอราคา : HH:MM น.`

## ⚠️ ข้อจำกัด/รายละเอียดสำคัญ
- **ไม่มีชื่อผู้ชนะ** ในเอกสารนี้ — มีแค่ "ราคาต่ำสุดที่เสนอ" + จำนวนผู้เสนอ. ชื่อมากับประกาศทางการ (getProcureResult, Round 2)
- **หลักเกณฑ์ราคา** → แสดงราคาต่ำสุด. **เกณฑ์ขั้นต่ำ (2 ซอง)** ตามระเบียบฯ ข้อ 83(3) → **ไม่แสดงราคา** (ต้องพิจารณาเทคนิคก่อน) → Round 1 = "มีผู้เสนอ N ราย รอผลทางการ" (no price)
- เอกสารนี้คือ "เบื้องต้น" — ผู้ชนะจริงต้องผ่านคณะกรรมการ + ประกาศทางการ (อาจไม่ใช่รายต่ำสุด ถ้าตัดสิทธิ์)
- announceType ใน greenBook list = `"price"` (วันที่ = วันเปิดเผย). ตรวจการมีอยู่ผ่าน greenBook `mode=LINK` ก่อน gen ได้

## probe scripts
- `scripts/_probe_capture_prelim_summary.py` (playwright capture, Chrome 9222)
- raw: `data/probe/prelim_capture_69059075454.json`

## ใช้ทำอะไรต่อ
Feature "แจ้ง W0 2 รอบ" (Option C): Round 1 เบื้องต้น (ราคาต่ำสุด + closed-loop เทียบ prediction) → Round 2 เต็ม (ผู้ชนะทางการ + คู่แข่ง การ์ดเดิม). ดู [[project_event_centric_queue]] (stage machine D0→PRELIM→W0).
