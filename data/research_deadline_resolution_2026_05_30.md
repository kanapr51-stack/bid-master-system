# Deadline Resolution Research — province_api (2026-05-30)

ปัญหา: หา bid submission deadline (วันยื่นข้อเสนอ) ของงาน province_api เพื่อทำ deadline gate

## ช่องทางที่ probe (project จริง)

### 1. JSON API — ไม่มี deadline
probe 69059341206 / 69059532519:
- province-search item: `announceDate, modifiedDate, announceWinnerDate, stepId, projectStatus`
- getProjectDetail.data: `projectId, methodId, typeId, stepId, projectStatus, flowSeqno, announceType` (ไม่มี date)
- getProcurementDetail.data: `reportDate, announceDate, questionFdate, procurePlanAnnounceDetailAnnounceDate, deliverDay` (ไม่มีวันยื่นซอง)

### 2. process3 (legacy) — มี HTML ประกาศ แต่ต้อง browser session
URL (จาก capture ตอนคลิกดูประกาศในเบราว์เซอร์):
```
https://process3.gprocurement.go.th/egp2procmainWeb/jsp/procsearch.sch
  ?pid=<projectId>&servlet=gojsp&proc_id=ShowHTMLFile&processFlows=Procure
```
- เบราว์เซอร์ render ได้ (เห็นเนื้อหาประกาศเต็ม)
- requests cold fetch → status 200 แต่ **len=0** แม้มี JSESSIONID/cookies → ต้อง multi-step JSP session flow (เหตุผลที่ของเดิมใช้ Selenium)

### 3. process5 greenBook — endpoint ทำงาน แต่ยัง crack param ไม่ได้
```
GET egp-atpj27-service/.../announcement/greenBook?mode=VIEW&methodId=X&tempProjectId=<pid>
  (ใช้ AES generateToken ไม่ใช่ search bearer)
```
- responseCode=0, data keys: `processDataAnnouncementTypeResponceList, alProcurePriceAndReceiveResponce, greenBookAnnouncementTypeLinkDto`
- **`alProcurePriceAndReceiveResponce`** น่าจะเป็นวันรับ/ยื่นซอง (Receive) แต่ = null กับ methodId=16 (D0 actives ทุกตัวในหน้า 1)
- เบราว์เซอร์ใช้ methodId=19 ตอนดูงานผู้ชนะ → methodId ต่างต่องาน (ยังไม่รู้ค่าที่ถูกของ D0 invitation)
- mode=LINK → data:{} ว่าง; mode=VIEW/PDF → มี structure แต่ list ว่าง

### 4. egp-template-service PDF — ต้อง templateId (UUID) ที่ยัง map ไม่ได้
```
GET egp-template-service/dwnt/view-pdf-file?templateId=<UUID>
```
- วิธีเดิม (patch_deadlines.py): templateId มาจาก RSS <link> → download PDF → pdfplumber → regex "ยื่นข้อเสนอ"
- province_api ไม่มี RSS link → ยังหา templateId จาก projectId ไม่ได้ (guess endpoint 404 หมด)

## สรุป
deadline มีจริง (HTML process3 / อาจใน greenBook JSON) แต่ยังดึง server-side สะอาดไม่ได้
ทางที่เหลือ: (A) crack greenBook param, (B) browser-render process3 ผ่าน Chrome เดิม, (C) build pipeline ก่อน เสียบ resolver ทีหลัง
