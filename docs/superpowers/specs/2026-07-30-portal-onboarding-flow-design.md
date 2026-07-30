# Portal Onboarding Flow (Profile → Settings → Notifications) — Design

**วันที่:** 2026-07-30
**สถานะ:** Approved (รอเขียน implementation plan)

## บริบท / ทำไมต้องทำ

ตอนนี้ `/portal` เปิดให้ login ผ่าน LINE ได้อยู่แล้ว แต่หลัง login ครั้งแรกจะพาไปหน้า `/portal/world` ทันที โดยไม่มีการบังคับให้กรอกข้อมูลส่วนตัวหรือเปิดรับแจ้งเตือนก่อน — ผลคือ:

- ลูกค้าใหม่ที่ล็อกอินอาจไม่เคยกรอกข้อมูลติดต่อ (userName/userGmail/userPhone/userLineId) เลย
- ลูกค้าใหม่อาจไม่เคยกดเปิด Web Push เลย เพราะการ์ดเปิดแจ้งเตือน (`PushNotifyCard`) เป็นแค่การ์ดเสริมในหน้าแรก ไม่ใช่ด่านบังคับ
- การแจ้งเตือนจริง (web push) ถูกล็อกด้วย `PUSH_ALLOWLIST` (env var บน Vercel) ให้ใช้ได้เฉพาะบัญชีทดสอบของคุณกัญจน์เท่านั้น — ต้องเคลียร์ค่านี้ก่อนเปิดใช้จริงกับลูกค้าคนอื่น

งานนี้คือสร้าง onboarding flow บังคับ 3 ขั้นหลัง login ครั้งแรก (และบังคับย้อนหลังกับบัญชีเก่าที่ยังไม่ผ่านด้วย) + แก้บั๊กที่พบระหว่างสำรวจโค้ด + เปิดการแจ้งเตือนให้ทุกบัญชีใช้ได้จริง

## Flow

```
LINE login สำเร็จ
      │
      ▼
[ยังไม่ผ่าน] หน้า /portal/profile (บังคับ)
  - กรอกครบ 4 ช่อง: ชื่อ-นามสกุล, Gmail, เบอร์โทรส่วนตัว, LINE ID
  - กด "บันทึกและดำเนินการต่อ" → ไปขั้นถัดไป
      │
      ▼
[ยังไม่ผ่าน] หน้า /portal/settings (บังคับ)
  - กรอก keyword / ช่วงงบ / SME-MIT / เวลาแจ้งเตือนเช้า-เย็น (ทุกช่องไม่บังคับ มีค่า default อยู่แล้ว)
  - จังหวัด: read-only เหมือนเดิม (แอดมินกำหนดให้) — ไม่เป็นเงื่อนไขผ่าน/ไม่ผ่าน
  - กด "บันทึกและดำเนินการต่อ" → ถือว่าขั้นนี้ "เสร็จ" (บันทึก timestamp) → ไปขั้นถัดไป
      │
      ▼
[ยังไม่ผ่าน] หน้า /portal/notifications (ใหม่)
  - อธิบายสั้นๆ ว่าทำไมต้องเปิด + ปุ่ม "เปิดการแจ้งเตือน" (ขอ browser permission จริง, subscribe web push)
  - ปุ่มรอง "ข้ามไปก่อน"
  - ทั้งสองปุ่ม (เปิดสำเร็จ / ข้าม / permission ถูกปฏิเสธ / browser ไม่รองรับ) → ถือว่าขั้นนี้ "ตัดสินใจแล้ว" → ผ่านเข้าระบบได้
  - ถ้าไม่ได้เปิดจริง (ข้าม/ปฏิเสธ/ไม่รองรับ) → หน้า /portal/world ยังคงมีการ์ดเตือนเดิม (PushNotifyCard) ให้กดเปิดทีหลังได้เสมอ
      │
      ▼
เข้าใช้งานปกติ (/portal/world และหน้าอื่นๆ ทั้งหมด)
```

**บัญชีเก่าที่มีอยู่แล้ว (รวมของคุณกัญจน์เอง):** ไม่ grandfather — ทุกบัญชีต้องผ่าน gate เดียวกัน โดยเช็คจากข้อมูลจริงที่มีอยู่ (ถ้ากรอกครบอยู่แล้วในระบบเก่า จะนับว่าผ่านขั้นนั้นทันทีโดยอัตโนมัติ ไม่ต้องกรอกซ้ำ — ดูหัวข้อ "เงื่อนไขผ่านแต่ละขั้น" ด้านล่าง)

## เงื่อนไขผ่านแต่ละขั้น (ตรวจจากข้อมูลจริง ไม่ใช่ flag แยกทุกอัน)

| ขั้น | เงื่อนไข "ผ่านแล้ว" | เก็บที่ไหน |
|---|---|---|
| Profile | `userName`, `userGmail`, `userPhone`, `userLineId` ทั้ง 4 ช่องไม่ว่าง | `notes.userName/userGmail/userPhone/userLineId` (มีอยู่แล้ว) |
| Settings | มี `notes.settingsConfirmedAt` (timestamp) | `notes.settingsConfirmedAt` (ฟิลด์ใหม่ ตั้งตอนกด "บันทึกการตั้งค่า") |
| Notifications | มี active push subscription จริง **หรือ** มี `notes.notificationsPromptDismissedAt` (timestamp) | push subscription เช็คจาก `push_subscriptions` table (ผ่าน API ใหม่) / `notes.notificationsPromptDismissedAt` (ฟิลด์ใหม่) |

Settings ตั้งใจใช้ explicit flag (ไม่ derive จากค่า keyword/งบ) เพราะค่าว่างหมดถือเป็นค่าที่ถูกต้อง (= รับแจ้งเตือนทุกงานในจังหวัด) แยกจาก "ยังไม่เคยเข้ามาตั้งค่าเลย" ไม่ได้ถ้าไม่มี flag

## การบังคับ (gate) แต่ละหน้า

โครงสร้างปัจจุบันของ `/portal/*` ไม่มี middleware กลาง — แต่ละ `page.tsx` (server component) เช็ค session cookie เองแล้ว `redirect('/portal/login')` ถ้าไม่มี session (ดู `profile/page.tsx`, `settings/page.tsx` เป็นตัวอย่าง)

จะเพิ่ม helper กลาง `getOnboardingRedirect(customer): string | null` ใน `dashboard/web/src/lib/onboarding.ts` คืนค่า path ที่ต้องเด้งไป (หรือ `null` ถ้าผ่านครบ) แล้วเรียกใช้ที่ต้นทุก `page.tsx` ที่เป็นหน้าใช้งานจริง (`world`, `jobs`, `job/[pid]`, `history`, `packages`, `company-stats`, `company/[tin]`, `documents`) — **ไม่เรียกใน** `profile`, `settings`, `notifications`, `login` (กันเด้งวนลูป)

แต่ละหน้าที่ต้อง gate จะมี pattern เพิ่มจากของเดิมแค่ 2 บรรทัด:
```ts
const redirectTo = getOnboardingRedirect(customer);
if (redirectTo) redirect(redirectTo);
```

## หน้า /portal/notifications (ใหม่)

- Server component ตรวจ session เหมือนหน้าอื่น, ถ้า onboarding ผ่านครบแล้ว (เข้ามาซ้ำ) → redirect `/portal/world`
- Client component ใหม่ `NotificationsClient.tsx` — reuse logic เดิมจาก `PushNotifyCard.tsx` (permission request, service worker register, subscribe, POST `/api/portal/push/subscribe`) แต่เป็น full-page พร้อมปุ่ม "ข้ามไปก่อน" ที่ยิง POST ไปตั้ง `notes.notificationsPromptDismissedAt`
- `PushNotifyCard.tsx` เดิมยังอยู่ในหน้า `/portal/world` เหมือนเดิม (เป็น fallback banner ถ้าข้าม/ปฏิเสธตอน onboarding — ไม่ต้องแก้)

## แก้บั๊ก: Profile save ล้าง Settings

**ปัญหาปัจจุบัน:** `profile/_client.tsx` `handleSave()` POST ไป `/api/portal/save` ด้วย body ที่มีแค่ `{userName, userGmail, userPhone, userLineId}` — endpoint `api/portal/save/route.ts` เอา body ทั้งก้อนไป `encodePortalNotes()` แล้วเขียนทับ `notes` column ทั้งคอลัมน์ ไม่ merge กับของเดิม → ล้าง `classes` (keyword/geo), `isSME`, `isMIT`, `notifyTime`, `morningNotifyTime`, `starred`, `documents` ที่เคยตั้งไว้

**แก้:** ให้ `ProfileClient.handleSave()` โหลด notes ปัจจุบัน (ส่งมาจาก server component เป็น prop อยู่แล้วบางส่วน — ต้องส่ง full `PortalNotes` ที่ parse แล้วเป็น prop เพิ่ม) แล้ว spread ทับเฉพาะ 4 ฟิลด์ที่แก้ก่อนส่ง:
```ts
body: JSON.stringify({ ...currentNotes, userName, userGmail, userPhone, userLineId })
```
เดียวกับที่ `settings/_client.tsx` ทำอยู่แล้ว (`{ ...notes, classes: toClasses(...), isSME, isMIT, notifyTime, morningNotifyTime }`) — ทำให้ทั้งสองหน้าใช้ pattern เดียวกัน (merge ฝั่ง client ก่อนส่ง)

Settings save (ขั้นตอนใหม่) จะเพิ่ม `settingsConfirmedAt` เข้าไปใน body เดียวกันนี้ทุกครั้งที่กดบันทึก (ไม่ใช่แค่ตอน onboarding — แก้ทีหลังก็ถือว่า "ยืนยันแล้ว" เหมือนกัน ไม่กระทบอะไรเพราะเช็คแค่ "มีค่าหรือไม่มี")

**ปุ่ม "ดำเนินการต่อ" vs ปุ่ม "บันทึก" ปกติ:** ทั้ง Profile และ Settings page (server component) จะรู้อยู่แล้วว่าตอนนี้ยัง onboarding ไม่เสร็จหรือเสร็จแล้ว (จาก `getOnboardingRedirect` ตัวเดียวกัน) — ส่ง prop `isOnboarding: boolean` ลงไปให้ client component ใช้ตัดสินใจ label ปุ่มและ action หลัง save สำเร็จ:
- `isOnboarding=true` (เข้ามาระหว่างทำ onboarding ยังไม่ครบ): label "บันทึกและดำเนินการต่อ" → save สำเร็จแล้ว `router.push()` ไปขั้นถัดไป
- `isOnboarding=false` (onboarding ผ่านครบแล้ว เข้ามาแก้ไขทีหลัง): label เดิม "บันทึกข้อมูลส่วนตัว" / "บันทึกการตั้งค่า" → save สำเร็จแล้วอยู่หน้าเดิม (พฤติกรรมปัจจุบัน ไม่เปลี่ยน)

## เปิดการแจ้งเตือนให้ทุกบัญชี

`dashboard/web/src/app/api/portal/push/subscribe/route.ts:20-24` มี `PUSH_ALLOWLIST` (env var, comma-separated line_user_id, ว่าง = เปิดทุกคน) ปัจจุบันตั้งไว้เฉพาะบัญชีคุณกัญจน์บน Vercel

**Action ตอน deploy (ไม่ใช่แก้โค้ด):** ลบ/เคลียร์ `PUSH_ALLOWLIST` ให้ว่างบน Vercel project settings — ทำหลังจาก onboarding flow ขึ้น production และทดสอบผ่านแล้วเท่านั้น (กันมีคนกด subscribe ก่อน flow พร้อม)

หน้า login (`/portal/login`) เปิดสาธารณะอยู่แล้ว ไม่ต้องแก้อะไรเพิ่มสำหรับ "เปิดให้คนนอกสมัครเอง"

## Error handling

- API `/api/portal/save` ล้มเหลว (network/500) → หน้า Profile/Settings แสดง error เดิม ไม่เปลี่ยนหน้า (ผู้ใช้กดใหม่ได้)
- Push subscribe ล้มเหลว (permission denied / browser ไม่รองรับ / API error) → ถือเป็น "ตัดสินใจแล้ว" เหมือนกด "ข้าม" ไม่ block onboarding
- `getOnboardingRedirect` ดึงข้อมูล customer ไม่ได้ (engine ล่ม) → fail-open ปล่อยเข้า (ตาม pattern เดิมของหน้าอื่นที่ `try { customer = ... } catch { /* ignore */ }`) — ไม่ให้ onboarding gate กลายเป็นจุดเดียวที่พังแล้วเข้าระบบไม่ได้เลย

## Testing / verification

- [ ] Login ด้วยบัญชีใหม่ (ยังไม่เคยมีใน `customers`) → ต้องเจอหน้า Profile ก่อน ไม่ใช่ /portal/world
- [ ] กรอก Profile ไม่ครบ 4 ช่อง แล้วพยายามเข้า `/portal/world` ตรงๆ (พิมพ์ URL) → ต้องถูกเด้งกลับ Profile
- [ ] กรอก Profile ครบ → ไป Settings → กด "บันทึกและดำเนินการต่อ" โดยไม่แก้อะไร → ต้องไปหน้า Notifications (ไม่ค้าง แม้ไม่มีจังหวัด)
- [ ] หน้า Notifications กด "เปิดการแจ้งเตือน" บน browser ที่รองรับ → permission popup ขึ้นจริง → subscribe สำเร็จ → เข้า /portal/world
- [ ] หน้า Notifications กด "ข้ามไปก่อน" → เข้า /portal/world ได้ → เห็นการ์ด PushNotifyCard ค้างอยู่
- [ ] บัญชีเก่าที่มี `notes.classes`/keyword ตั้งไว้แล้ว: กรอก Profile (4 ช่องที่ขาด) แล้วกด save → เช็คว่า `notes.classes` ไม่หาย (regression test บั๊กที่แก้)
- [ ] เช็ค `data/bms_customers.db` (หรือผ่าน bms_api) ว่า `notes` column ของบัญชีทดสอบไม่ถูก JSON คนละก้อนทับกันระหว่างขั้นตอน
- [ ] เคลียร์ `PUSH_ALLOWLIST` ใน staging แล้วทดสอบ subscribe ด้วยบัญชี LINE อื่นที่ไม่ใช่คุณกัญจน์ → ต้องไม่โดน 403

## Out of scope (ตัดออกจากรอบนี้)

- ไม่สร้างหน้า self-serve เลือกจังหวัดเอง (ยังเป็นงานแอดมินเหมือนเดิม)
- ไม่แตะ LINE push (LINE Notify/Messaging API) — งานนี้โฟกัสที่ web push บนบอร์ดซึ่งเป็นช่องหลักตามมติ 2026-07-21
- ไม่ทำ invite code / approval gate ก่อนสมัคร (หน้า login เปิดสาธารณะอยู่แล้ว)
