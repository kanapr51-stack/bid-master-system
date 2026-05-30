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

## Experiment 1 (CDP Renderability) — NEGATIVE (2026-05-30)
ทดสอบ 8 invitation projects (stepId M03/S01), CDP navigate ตรงไป process3 ShowHTMLFile:
- ทุกงาน render = **0 ตัวอักษร** (body ว่าง)
- diagnostic: final URL ไม่ redirect, title='', outerHTML=39 ('<html><head></head><body></body></html>'), frames=0
→ **cold CDP navigate ไม่ render** (เหมือน cold HTTP fetch) = ต้อง session state จาก click-through flow
→ Exp2 deadline_presence_rate วัดไม่ได้ (เพราะ render ไม่ออก)

**สรุป Exp1:** BrowserDeadlineProvider แบบ "navigate ตรง" = ตกทันที
human click-through ได้ (process5 detail → คลิกดูประกาศ → process3 render) แต่ replicate = ต้อง
automate click-through flow (DOM interaction + cross-window) = fragile/ช้า — หรือ capture request ที่ตั้ง session ก่อน ShowHTMLFile

## ทางที่เหลือ (resolver)
1. greenBook RE — mode=VIEW มี greenBookAnnouncementTypeLinkDto (อาจคืน templateId → ใช้ PROVEN PDF path!) แต่ methodId ยังผิด (16 ว่าง, winner ใช้ 19)
2. full click-through CDP automation (fragile)
3. NullDeadlineProvider + fail-closed ก่อน (pipeline deploy ได้, beta เงียบ — agreed)

## ⚠️ Lesson: greenBook brute-sweep trip WAF (2026-05-30)
ลอง brute methodId×mode×page (~360 req รัวๆ) → eGP WAF "Request Rejected (support ID)"
= error คลาสเดียวกับ throttle ก่อนหน้า (hammering). ❌ ห้าม brute param space รัวๆ
→ วิธีถูก: **capture call จริงของ browser ครั้งเดียว** (full URL + response body) ตอนดู INVITATION announcement
  = 1 call ไม่ใช่ 360, ผ่าน UI ปกติ ไม่ trip WAF, ได้ทั้ง param ที่ถูก + response จริง

## greenBook breakthrough (param ถูก) — 2026-05-30
capture จริง: `greenBook?mode=LINK&methodId=<projMethodId>&tempProjectId=<pid>&pageAnnounceType=<announceTypeCode>`
- param ที่ขาดคือ **pageAnnounceType** (= announceType text code เช่น W0) ไม่ใช่ pageAnnounce
- responseCode 0, `greenBookAnnouncementTypeLinkDto` = list มีจริง (3 entries สำหรับ W0 winner)
- DTO[0] fields: projectId, announceType, seqNo, **attachSumulate, partFile, attachName** (=document link, null สำหรับ W0 นี้),
  announceDate, methodId, typeId, templateType=W2, announceFlag, no, **filePath**(null), **token**(null), announceTypeName
→ field ที่น่าจะเป็น document linkage: **partFile / filePath / attachName / token** (W0 เฉพาะเจาะจง = null หมด)
→ **ยังไม่ได้ทดสอบ INVITATION (ประกาศเชิญชวน D0)** — user คลิกโดน winner ทุกรอบ

## RESUME POINT (ต่อจากนี้)
1. หา invitation announceType code: getProjectDetail/search ของงาน ประกวดราคา ที่ stepId active (M*/S*)
   → announceType text code ของมัน (ไม่ใช่ W0/B0)
2. เรียก greenBook(mode=LINK, methodId=<proj>, tempProjectId=<pid>, pageAnnounceType=<invitation code>)
   → ดูว่า partFile/filePath/attachName/token populate ไหม = templateId/PDF link
3. ถ้า populate → fetch PDF → pdfplumber (patch_deadlines) → deadline → GreenBookDeadlineProvider
4. ถ้า null อีก → greenBook ไม่พก invitation doc → fallback CDP click-through
⚠️ ห้าม brute param รัวๆ (trip WAF) — capture browser call หรือยิงทีละ call ห่างๆ
