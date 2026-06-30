# Design: บอร์ด /portal/world — section "งานใหม่ที่แมตช์" (Phase 2 discovery + per-user keyword matching)

วันที่: 2026-06-30
ที่มา: บอร์ด B (`bid-master-dashboard.vercel.app/portal/world`, Next.js) เป็นตัวหลักแล้ว (N+176→179). Phase 1 (`2026-06-30-portal-real-jobs-design.md`) ทำ section "งานที่ติดตาม" (followed_jobs) เสร็จ. Phase 2 = section discovery "งานใหม่ที่แมตช์" + ทำให้ keyword/งบ ราย user มีผลจริง. ดู [[project_customer_store_split]] [[project_matching_design]] [[project_beta_golive_strategy]]
อนุมัติ (กัญจน์ 2026-06-30): design ทั้งหมดด้านล่าง — scope = discovery board เท่านั้น (ไม่แตะ LINE pipeline), รวมงาน D0 + B0

## เป้าหมาย
1. เพิ่ม section **"✨ งานใหม่ที่แมตช์"** บน `/portal/world` — โชว์งานประมูลที่ตรง **พื้นที่ + คำค้น + งบ ของ user** แต่ **ยังไม่ได้ติดตาม** (query `projects_seen` ทั่วประเทศ)
2. ทำให้ keyword / budget ที่ user ตั้งในหน้า "บริษัท" (`notes.classes[]`) **มีผลจริง** กับการกรอง (ปัจจุบัน engine ใช้แค่ province) — แต่จำกัดผลที่ **board discovery เท่านั้น**
3. การ์ด discovery กด **"ติดตาม"** → ดึงงานเข้า `followed_jobs` → ย้ายไป section "งานที่ติดตาม" (= action loop ของ North-Star)

## หลักการ scope (สำคัญสุด — กำหนดความเสี่ยง)
- **Additive + read-only**: เป็น query ใหม่บนข้อมูลที่มีอยู่. **ไม่แตะ `config/matching_preferences.json` (global) และไม่แตะ LINE notification pipeline เลย** — delivery จริงของ pilot กัญจน์/ณฐมน/Mr.suvit ทำงานเหมือนเดิมทุกอย่าง
- per-user keyword matching เกิดขึ้น **ใน discovery query เท่านั้น** ไม่ใช่ rewrite pipeline เป็น per-tenant (defer ตาม [[project_matching_per_tenant_debt]] จนรับ tenant ต่างสายธุรกิจจริง)

## Success criteria (วัดได้)
1. user ที่ตั้ง provinces + keywords → `/portal/world` โชว์งาน D0 (ยื่นซองได้) + B0 (วางแผน) ในจังหวัดที่ subscribe ที่ match ≥1 keyword, **ไม่มีงานที่ติดตามแล้วซ้ำ**ใน section นี้
2. การ์ดโชว์ `matchedKeywords` (คำค้นของ user ที่โดน) ตรงกับชื่องานจริง
3. กด "ติดตาม" บนการ์ด discovery → row ใน `followed_jobs` เป็น `status='active'`; โหลดบอร์ดใหม่ → งานโผล่ใน "งานที่ติดตาม" + **หายจาก discovery**
4. user ตั้ง `budgetMin/MaxBaht` → งานนอกช่วงงบถูกกรองออก; ไม่ตั้ง → ไม่กรองงบ
5. งานที่ติด negative keyword (global safety net) ถูกตัดออกจาก discovery
6. user ที่**ไม่มี keyword/พื้นที่** → เห็น empty state ชวนไปตั้งค่า (ไม่ error, ไม่โชว์งานมั่ว)
7. `config/matching_preferences.json` และ LINE pipeline ไม่ถูกแก้ — verify ด้วย git diff (ไฟล์ pipeline/config ไม่เปลี่ยน)

## ขอบเขต
**ใน:** โมดูล `discovery_match`, endpoint `GET /api/portal/discover` + `POST /api/portal/follow`, helper `_classes_from_notes`, section UI ใหม่ + ปุ่มติดตาม, empty states, extract location/deadline helper ร่วมกับ `_portal_jobs`
**ไม่ใน (defer):** เปลี่ยน LINE pipeline เป็น per-user · per-tenant negative_keywords · รัศมี (radiusKm) เป็นตัวกรอง (Phase นี้ใช้ province-level; radius defer เพราะ projects_seen ไม่มีพิกัดงานเชื่อถือได้) · district/tambon-level discovery (projects_seen เก็บแค่ province เชื่อถือได้) · ranking ด้วย price prediction

## สถาปัตยกรรม / Data flow
```
browser (LINE LIFF, session line_user_id)
  → Next.js world/page.tsx (server)
      → lib/portal-jobs.ts getDiscoverJobs()  fetch(BMS_API_URL + X-BMS-Secret)
          → bms_api GET /api/portal/discover?line_user_id=
              → provinces (subscription_provinces) + keywords/budget (notes.classes)
              → query projects_seen WHERE province IN (...)
              → discovery_match.match() ต่อ row  (reuse job_matcher._kw_hit + guards + negative)
              → คืน {biddable:[...], planning:[...]} (ตัด followed แล้ว)
  → WorldClient render section "งานใหม่ที่แมตช์"
  ปุ่ม "ติดตาม" → POST /api/portal/follow {line_user_id, project_id}
              → _record_follow() → followed_jobs (status='active')
```
ทางที่ตัด: per-user pipeline rewrite (เสี่ยง+ยังไม่จำเป็น), radius matching (ไม่มีพิกัดงาน), Next.js query SQLite ตรง (DB อยู่ VPS).

## โมดูลใหม่ `scripts/discovery_match.py` (pure function — เทสต์แยกได้)
หน้าที่เดียว: ตัดสินว่า project 1 row match preference ของ user 1 คนไหม + คืนคำที่โดน. **ไม่แตะ DB, ไม่เรียก API** (caller ส่งข้อมูลมาให้)

```python
def match(project_name: str, project_province: str, project_budget: int,
          user_provinces: list[str], user_keywords: list[str],
          budget_min: int = 0, budget_max: int = 0,
          neg_keywords: list[str] = None) -> tuple[bool, list[str]]:
    """คืน (matched, matched_keywords).
    - province AND: project_province ต้องอยู่ใน user_provinces (normalize ก่อนเทียบ)
    - keyword OR: คำใดใน user_keywords ที่ _kw_hit(k, normalized_name) → เก็บใน matched_keywords
      (reuse job_matcher._kw_hit + _KEYWORD_GUARDS — ไม่เขียน guard ซ้ำ)
    - negative safety net: ถ้าชื่อมี neg_keyword ใด → ไม่ match (กัน garbage)
    - budget: ถ้า budget_min>0 และ project_budget < budget_min → ตัด; budget_max เดียวกัน
              (project_budget=0 = ไม่รู้ราคากลาง → ผ่าน ไม่ตัดทิ้ง)
    matched = province✓ AND keyword≥1 AND ไม่ติด negative AND อยู่ในช่วงงบ
    """
```
- import จาก `job_matcher`: `_kw_hit`, `_KEYWORD_GUARDS` (หรือเรียกผ่าน `_kw_hit` เลย), `normalize_thai` (ผ่าน text_normalize)
- `neg_keywords` default = โหลดจาก `job_matcher.load_config()["negative_keywords"]` (global safety net — ค่าคงที่ generic garbage filter)

## Helper ใหม่ `_classes_from_notes(notes_str)` ใน bms_api (คู่กับ `_provinces_from_notes` เดิม)
```python
def _classes_from_notes(notes_str: str) -> dict:
    """รวม preference ราย user จาก notes.classes[] → {keywords:[...], budget_min:int, budget_max:int}.
    - keywords = union ของ classes[].keywords (+ defaultKeywords) unique
    - budget_min = min ของ classes[].budgetMinBaht ที่ >0 (0 = ไม่ตั้ง)
    - budget_max = max ของ classes[].budgetMaxBaht ที่ >0
    parse ไม่ได้ → {keywords:[], budget_min:0, budget_max:0}"""
```
หมายเหตุ: provinces ยังดึงจาก `subscription_provinces` (source of truth ที่ POST /customer แตกไว้แล้ว) ไม่ใช่จาก notes — กันค่าเพี้ยน. keyword/budget ดึงจาก notes เพราะ engine ไม่มี column เก็บ (ตรงกับ [[project_customer_store_split]] defer note)

## Endpoint `GET /api/portal/discover?line_user_id=` (bms_api, pattern X-BMS-Secret เดิม)
1. verify secret → หา customer; ไม่เจอ → `{ok:true, jobs:{biddable:[], planning:[]}}`
2. provinces = subscription_provinces ของ customer; keywords/budget = `_classes_from_notes(notes)`
3. **ถ้า provinces ว่าง หรือ keywords ว่าง → คืน groups ว่าง** (web โชว์ empty state "ตั้งค่าก่อน")
4. followed set = `SELECT project_id FROM followed_jobs WHERE customer_id=?` (**ทุก status** — กัน re-suggest งานที่ unfollow แล้ว)
5. candidate = `SELECT project_id, project_name, announce_type, province, budget FROM projects_seen WHERE province IN (...)`
6. stage gate ต่อ row:
   - **biddable**: `announce_type='D0'` + resolve deadline (project_locations → project_enrichments fallback) + `deadline >= today`
   - **planning**: `announce_type` ขึ้นต้น `'B'` + `job_matcher.tor_is_fresh(first_seen_at, days=14)` (กัน B0 backlog ท่วม)
   - อื่น → skip
7. รัน `discovery_match.match(...)` → ผ่าน → ทำการ์ด; ตัด pid ที่อยู่ใน followed set
8. sort: biddable = deadline น้อย→มาก (ใกล้ปิดก่อน); planning = first_seen ใหม่→เก่า. limit **30/กลุ่ม**
9. enrich การ์ด (location/deadline/budget) — **extract helper `_job_location(conn, pid, prov)`** จาก logic ใน `_portal_jobs` (line ~415-445) มาใช้ร่วม (ลด duplication, ไฟล์ bms_api ยาวขึ้น)

## Endpoint `POST /api/portal/follow {line_user_id, project_id}` (bms_api)
- verify secret → `_record_follow(line_user_id, project_id)` (reuse, line ~227); ไม่เจอ customer → 404
- คืน `{ok:true, followed:true}`
- (unfollow ไม่อยู่ใน Phase นี้ — discovery card มีแค่ "ติดตาม"; unfollow ทำใน tracked section ภายหลัง defer)

## รูปข้อมูล DiscoverJob (JSON)
```
{
  project_id: string
  name: string
  location: string          // "ต.x อ.y จ.z" (เท่าที่ resolve ได้; อย่างน้อยมีจังหวัด)
  province: string
  deadline: string          // D0 เท่านั้น (planning ว่างได้)
  deadline_time: string
  budget: number            // ราคากลาง (อาจ 0)
  stage: 'biddable' | 'planning'
  matched_keywords: string[] // คำค้นของ user ที่โดน → ชิปบนการ์ด
}
```
(ไม่มี pred_lo/hi, winner — งาน discovery ยังไม่เข้า lifecycle tracking; days_left คำนวณฝั่ง web จาก deadline)

## Frontend (dashboard/web)
> ⚠️ `dashboard/web/AGENTS.md`: Next.js เวอร์ชันนี้มี breaking changes — **อ่าน `node_modules/next/dist/docs/` ที่เกี่ยวข้องก่อนเขียนโค้ด web**

- `lib/portal-jobs.ts`: เพิ่ม `getDiscoverJobs(lineUserId)` (fetch `/api/portal/discover`, X-BMS-Secret, server-side); type `DiscoverJob`
- route handler ใหม่ `app/api/portal/follow/route.ts`: relay session line_user_id → engine `POST /api/portal/follow` ด้วย secret (ไม่ส่ง secret ออก client)
- `world/page.tsx`: fetch discover jobs server-side คู่กับ tracked jobs; ส่งเข้า client
- `world/_client.tsx`: section ใหม่ "✨ งานใหม่ที่แมตช์" (วางหลัง/ก่อน tracked ตามน้ำหนัก UI)
  - การ์ด: ชื่อ, location, ชิป `matched_keywords`, งบ, นับถอยหลัง deadline (biddable), badge stage (🔵 ยื่นซองได้ / ⚪ วางแผน), ปุ่ม **"ติดตาม"** (+ ⭐ ถ้าต้องการ)
  - กด "ติดตาม" → POST `/api/portal/follow` → optimistic ย้ายการ์ดออกจาก discovery (หรือ refresh) → โผล่ใน tracked รอบหน้า
- empty states:
  - ไม่ตั้ง keyword/พื้นที่ → "ตั้งค่าพื้นที่และคำค้นในหน้าบริษัท เพื่อให้ระบบหางานที่ตรงให้คุณ" + ลิงก์หน้าบริษัท
  - ตั้งแล้วไม่เจอ → "ยังไม่มีงานใหม่ที่ตรงเกณฑ์วันนี้ — ระบบจะอัปเดตให้เมื่อมีงานเข้า"

## ปุ่ม "ติดตาม" vs ⭐ (แยกชั้น)
- **⭐ (job_stars)** = "สนใจ/ปักหมุด" ชั้นที่ 2 — มีอยู่แล้ว (POST /api/portal/star), ใช้ได้ทั้ง tracked + discovery, **ไม่ดึงเข้า lifecycle**
- **"ติดตาม" (followed_jobs)** = ดึงงานเข้าระบบเฝ้า lifecycle (เตือนใกล้ปิด/รู้ผล) — เฉพาะ discovery card
- การ์ด discovery มีทั้งสองได้: ⭐ = ปักหมุดเฉยๆ, "ติดตาม" = เอาเข้าระบบ

## Auth / security
line_user_id จาก session cookie (server-side) + X-BMS-Secret (env Vercel ↔ VPS .env, ตั้งไว้แล้ว). secret ไม่ออก client — fetch เกิดฝั่ง server/route handler เท่านั้น (เหมือน Phase 1)

## Error handling
- engine ล่ม/secret ผิด → section discovery โชว์ empty state + log (ไม่ crash หน้า world, try/catch เหมือน getPortalJobs)
- follow ล้มเหลว → revert UI + เงียบ (ไม่ block)
- provinces/keywords ว่าง → empty state (ไม่ query projects_seen)

## Testing
- **discovery_match** (unit, pure): keyword OR หลายคำ, guard "ท่อ"/"ราง" (ไม่ false-match), province AND (ตัดจังหวัดอื่น), budget min/max (รวม budget=0 ผ่าน), negative ตัด, คืน matched_keywords ถูก
- **bms_api `/api/portal/discover`** (scratch DB copy, BMS_DATA_DIR — **ห้ามแตะ prod**): seed customer + subscription_provinces + notes.classes + projects_seen (D0 in/out window, B0 fresh/stale, งานที่ followed แล้ว) → assert biddable/planning ถูกกลุ่ม, ตัด followed, ตัดนอกพื้นที่/นอก keyword; provinces ว่าง → groups ว่าง; secret ผิด → 403
- **bms_api `/api/portal/follow`** (scratch DB): follow → followed_jobs active; discover รอบถัดไปไม่มี pid นั้น; ไม่มี customer → 404
- **web**: tsc ผ่าน; throwaway follow ผ่านบอร์ด → เช็ค followed_jobs → cleanup
- **sanity (Sophia)**: หลังแก้ bms_api ก่อน commit — duplicate, test-data, queue ไม่เพี้ยน, customers ยัง 5/0

## Deploy
scp `bms_api.py` + `discovery_match.py` → VPS root@45.76.156.166 (`~/.ssh/bms_vps`) + restart `bms-api.service`; `cd dashboard/web && vercel deploy --prod --yes`. commit+push + reconcile VPS git (stash+ff-pull, `git diff --ignore-cr-at-eol` กัน CRLF หลอก — ดู [[project_deploy_debt]])

## Out of scope / defer
- LINE pipeline per-user (เสี่ยง, ยังไม่จำเป็น — [[project_matching_per_tenant_debt]])
- radius (radiusKm) เป็นตัวกรอง — projects_seen ไม่มีพิกัดงานเชื่อถือได้
- district/tambon-level discovery — projects_seen เก็บ province เชื่อถือได้เท่านั้น
- ranking ด้วย price prediction / win-rate
- unfollow บน discovery (มีแค่ "ติดตาม")
- per-tenant negative_keywords

## หมายเหตุความคาดหวัง (จาก [[project_rss_is_nationwide]])
งานก่อสร้าง 2 จังหวัด (นครพนม+บึงกาฬ) ที่ตรงเกณฑ์จริง ~1-2/วัน → section นี้ปกติจะมีงานน้อย บางวันว่าง = ไม่ใช่บั๊ก. value = "เห็นงานที่ไม่เคยเห็น แม้แค่ 1 งาน" ([[project_beta_golive_strategy]])
