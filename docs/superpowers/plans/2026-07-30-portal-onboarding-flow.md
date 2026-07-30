# Portal Onboarding Flow (Profile → Settings → เปิดแจ้งเตือน) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** หลัง LINE login ครั้งแรก (และบัญชีเก่าที่ยังไม่ผ่าน) บังคับผ่าน 3 ขั้นตามลำดับ — กรอกโปรไฟล์ครบ → ยืนยันตั้งค่า → ตัดสินใจเรื่องแจ้งเตือน (เปิดจริง/ข้ามไปก่อน) — ก่อนเข้าใช้งานหน้าอื่นของ `/portal` ได้ พร้อมแก้บั๊กที่ปุ่มบันทึกโปรไฟล์ล้างการตั้งค่าเดิม และเปิด Web Push ให้ทุกบัญชีใช้ได้จริง (ไม่ใช่แค่บัญชีทดสอบ)

**Architecture:** เพิ่ม helper กลาง `dashboard/web/src/lib/onboarding.ts` (`nextOnboardingPath` ฟังก์ชัน pure ตัดสินจากข้อมูล customer จริง, `requireOnboarding` เรียกใช้จากหน้าใช้งานทั่วไปเพื่อ fetch customer + redirect ถ้ายังไม่ผ่าน) หน้า Profile/Settings/Notifications (ใหม่) เช็คลำดับของตัวเองแล้วส่ง `isOnboarding` ลง client component เพื่อสลับ label ปุ่ม/พฤติกรรมหลัง save ระหว่าง "บันทึกและดำเนินการต่อ" (onboarding) กับ "บันทึก" ปกติ (แก้ทีหลัง) สถานะแต่ละขั้นอ่านจากข้อมูลจริงที่มีอยู่แล้ว (ฟิลด์โปรไฟล์, `notes.settingsConfirmedAt`, `notes.notificationsPromptDismissedAt`, push subscription จริง) ไม่ต้องแก้ schema DB

**Tech Stack:** Next.js (dashboard/web, Vercel) · FastAPI (`scripts/bms_api.py`, VPS) · SQLite (`Sebastian_Customer_DB`) · Web Push (VAPID, มีอยู่แล้ว)

**Spec:** `docs/superpowers/specs/2026-07-30-portal-onboarding-flow-design.md`

## Global Constraints

- **ห้าม push origin / deploy โดยไม่ confirm คุณกัญจน์ก่อน** (Task 8 มี gate)
- Python tests = สคริปต์ standalone `scripts/test_*.py` รันด้วย `python scripts/test_X.py` จบด้วย `print("PASS ...")` (pattern เดิมของ repo — ไม่มี pytest/conftest)
- `dashboard/web` **ไม่มี test framework ติดตั้งเลย** (ไม่มี jest/vitest, `package.json` scripts มีแค่ dev/build/start) — งานฝั่งนี้ verify ด้วย `npm run build` (type check) + manual click-through ตาม precedent เดิม (`docs/superpowers/plans/2026-07-14-web-push-notification.md` Task 6/7) ห้ามติดตั้ง test framework ใหม่เพิ่มเองในงานนี้ (นอกสโคป)
- ทุกจุดที่เขียนไป `/api/portal/save` **ต้อง spread `...notes` เดิมก่อนเสมอ** — endpoint นี้ overwrite `notes` column ทั้งคอลัมน์ ไม่ merge ให้ (นี่คือบั๊กที่กำลังแก้ในงานนี้ — ห้ามพลาดจุดใหม่ที่เพิ่ม)
- Engine: `https://api.butler-bms.com` · บอร์ด: `https://bid-master-dashboard.vercel.app`
- ทุก commit → entry ใน `progress_log.md` ก่อน + Discord notify หลัง (กฎ CLAUDE.md) — งานนี้รวมเป็น entry เดียว อัปเดตท้าย Task 8
- `PUSH_ALLOWLIST` เป็นค่าบน Vercel project env เท่านั้น — ห้าม hardcode ในโค้ด/commit

---

### Task 1: Backend — `has_push_subscription` ใน `GET /api/portal/customer`

**Files:**
- Modify: `scripts/bms_api.py:1479-1512` (`portal_get_customer`)
- Test: `scripts/test_portal_customer_push_status.py`

**Interfaces:**
- Produces: response field `customer.has_push_subscription: bool` — Task 2 (frontend `customers.ts`) consumes ชื่อฟิลด์นี้ตรงๆ

- [ ] **Step 1: เขียน failing test**

```python
# scripts/test_portal_customer_push_status.py
"""GET /api/portal/customer คืน has_push_subscription: true เมื่อมี push_subscriptions ที่ยัง active,
false เมื่อไม่มี หรือถูก disable แล้วทั้งหมด"""
import os, sys, asyncio, tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp())
os.environ.update(BMS_DATA_DIR=str(SCRATCH), BMS_DB_PATH=str(SCRATCH / "bms_customers.db"),
                  BMS_INTERNAL_SECRET="t")
sys.path.insert(0, str(Path(__file__).parent))

import Sebastian_Customer_DB as db
db.init_schema()
import bms_api

NOW = "2026-07-30T00:00:00+07:00"


async def main():
    with bms_api.get_conn() as conn:
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, active, created_at, updated_at) "
                     "VALUES ('UNOSUB','x','trial',1,?,?)", (NOW, NOW))
        conn.execute("INSERT INTO customers (line_user_id, display_name, tier, active, created_at, updated_at) "
                     "VALUES ('UHASSUB','y','trial',1,?,?)", (NOW, NOW))
        cid = conn.execute("SELECT id FROM customers WHERE line_user_id='UHASSUB'").fetchone()["id"]
        conn.execute("INSERT INTO push_subscriptions (customer_id, endpoint, p256dh, auth, created_at) "
                     "VALUES (?, 'https://push.example/e1', 'pk', 'ak', ?)", (cid, NOW))

    r = await bms_api.portal_get_customer(line_user_id="UNOSUB", x_bms_secret="t")
    assert r["customer"]["has_push_subscription"] is False, r

    r = await bms_api.portal_get_customer(line_user_id="UHASSUB", x_bms_secret="t")
    assert r["customer"]["has_push_subscription"] is True, r

    # disabled subscription ไม่นับว่า active
    with bms_api.get_conn() as conn:
        conn.execute("UPDATE push_subscriptions SET disabled_at=? WHERE customer_id=?", (NOW, cid))
    r = await bms_api.portal_get_customer(line_user_id="UHASSUB", x_bms_secret="t")
    assert r["customer"]["has_push_subscription"] is False, r

    # ลูกค้าไม่มีในระบบ → customer เป็น None ไม่ crash
    r = await bms_api.portal_get_customer(line_user_id="UNKNOWN", x_bms_secret="t")
    assert r["customer"] is None, r

    print("PASS test_portal_customer_push_status")


asyncio.run(main())
```

- [ ] **Step 2: รันให้ fail**

Run: `python scripts/test_portal_customer_push_status.py`
Expected: FAIL — `AssertionError` หรือ `KeyError: 'has_push_subscription'` (ฟิลด์ยังไม่มีใน response)

- [ ] **Step 3: แก้ `portal_get_customer`**

ใน `scripts/bms_api.py` แก้บล็อกนี้ (บรรทัด ~1479-1489 ปัจจุบัน):

```python
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, line_user_id, display_name, email, phone, tier, active, "
            "created_at, updated_at, notes, expires_at FROM customers WHERE line_user_id=?",
            (line_user_id,),
        ).fetchone()
        # N+198.1: จังหวัดที่ subscribe จริง (source of truth ของ "พื้นที่ครอบคลุม" — ไม่ใช่ notes.classes)
        provinces = [r["province"] for r in conn.execute(
            "SELECT sp.province FROM subscription_provinces sp "
            "JOIN subscriptions s ON s.id=sp.subscription_id WHERE s.customer_id=?",
            (row["id"],)).fetchall()] if row else []
        # เช็คว่ามีเครื่องที่ยังเปิดรับ web push อยู่ไหม (onboarding gate ฝั่งบอร์ดใช้เช็คขั้น "เปิดแจ้งเตือน")
        has_push_subscription = bool(row) and conn.execute(
            "SELECT 1 FROM push_subscriptions WHERE customer_id=? AND disabled_at IS NULL LIMIT 1",
            (row["id"],)).fetchone() is not None
```

แล้วเพิ่ม `"has_push_subscription": has_push_subscription,` เข้าไปใน dict ที่ return (ต่อจากบรรทัด `"provinces": provinces,`):

```python
    return {"ok": True, "customer": {
        "line_user_id": row["line_user_id"],
        "display_name": row["display_name"] or "",
        "email": row["email"] or "",
        "phone": row["phone"] or "",
        "tier": row["tier"] or "trial",
        "status": "active" if row["active"] else "inactive",
        "registered_at": row["created_at"] or "",
        "last_active_at": row["updated_at"] or "",
        "expires_at": expires_at,
        "notes": row["notes"] or "",
        "provinces": provinces,
        "has_push_subscription": has_push_subscription,
    }}
```

- [ ] **Step 4: รันให้ pass + regression**

Run: `python scripts/test_portal_customer_push_status.py && python scripts/test_push_api.py`
Expected: `PASS test_portal_customer_push_status` และ `PASS test_push_api` ทั้งคู่

- [ ] **Step 5: Commit**

```bash
git add scripts/bms_api.py scripts/test_portal_customer_push_status.py
git commit -m "feat(portal): เพิ่ม has_push_subscription ใน GET /api/portal/customer (onboarding gate)"
```

---

### Task 2: Frontend — types + `lib/onboarding.ts`

**Files:**
- Modify: `dashboard/web/src/lib/customers.ts` (เพิ่ม `has_push_subscription` ใน `Customer`/`EngineCustomer`/`toCustomer`)
- Modify: `dashboard/web/src/lib/portal-data.ts` (เพิ่ม `settingsConfirmedAt`, `notificationsPromptDismissedAt` ใน `PortalNotes`)
- Create: `dashboard/web/src/lib/onboarding.ts`

**Interfaces:**
- Consumes: `Customer` type + `getCustomerByLineId` (`lib/customers.ts`), `parsePortalNotes` (`lib/portal-data.ts`)
- Produces (Task 3/4/5/6 เรียกใช้ตรงๆ):
  - `nextOnboardingPath(customer: Customer | null): string | null` — คืน `'/portal/profile'` | `'/portal/settings'` | `'/portal/notifications'` | `null` (ผ่านครบ)
  - `requireOnboarding(lineUserId: string): Promise<Customer | null>` — fetch customer, redirect ถ้ายังไม่ผ่าน, คืน customer ถ้าผ่านหรือ engine ล่ม (fail-open)

- [ ] **Step 1: แก้ `customers.ts`**

ใน `dashboard/web/src/lib/customers.ts` เพิ่มฟิลด์ในทั้ง 3 จุด:

```typescript
export interface Customer {
  line_user_id: string;
  display_name: string;
  email: string;
  phone: string;
  จังหวัด: string;
  อำเภอ: string;
  keywords: string;
  tier: string;
  status: string;
  registered_at: string;
  expires_at: string;
  last_active_at: string;
  notes: string;
  provinces: string[];
  has_push_subscription: boolean; // มีเครื่องที่ยังเปิดรับ web push อยู่ไหม (onboarding gate)
}
```

```typescript
interface EngineCustomer {
  line_user_id: string;
  display_name?: string;
  email?: string;
  phone?: string;
  tier?: string;
  status?: string;
  registered_at?: string;
  last_active_at?: string;
  expires_at?: string;
  notes?: string;
  provinces?: string[];
  has_push_subscription?: boolean;
}
```

```typescript
function toCustomer(e: EngineCustomer): Customer {
  return {
    line_user_id: e.line_user_id,
    display_name: e.display_name ?? "",
    email: e.email ?? "",
    phone: e.phone ?? "",
    จังหวัด: "",
    อำเภอ: "",
    keywords: "",
    tier: e.tier ?? "",
    status: e.status ?? "trial",
    registered_at: e.registered_at ?? "",
    expires_at: e.expires_at ?? "",
    last_active_at: e.last_active_at ?? "",
    notes: e.notes ?? "",
    provinces: e.provinces ?? [],
    has_push_subscription: e.has_push_subscription ?? false,
  };
}
```

- [ ] **Step 2: แก้ `portal-data.ts`**

ใน `dashboard/web/src/lib/portal-data.ts` แก้ `interface PortalNotes` (เพิ่ม 2 บรรทัดท้าย `userLineId`):

```typescript
export interface PortalNotes {
  classes?: BusinessClass[];
  tierId?: string;
  chatUsed?: number;
  budgetMin?: number;
  budgetMax?: number;
  isSME?: boolean;
  isMIT?: boolean;
  notifyTime?: string;
  morningNotifyTime?: string;
  starred?: string[];
  documents?: Record<string, DocumentFile[]>;
  userName?: string;
  userGmail?: string;
  userPhone?: string;
  userLineId?: string;
  settingsConfirmedAt?: string;             // ตั้งตอนกด "บันทึกการตั้งค่า" ครั้งแรก — onboarding gate ขั้น 2
  notificationsPromptDismissedAt?: string;  // ตั้งตอนกด "ข้ามไปก่อน" ในหน้าเปิดแจ้งเตือน — onboarding gate ขั้น 3
}
```

- [ ] **Step 3: สร้าง `lib/onboarding.ts`**

```typescript
// dashboard/web/src/lib/onboarding.ts
/**
 * Onboarding gate: profile → settings → notifications ต้องผ่านตามลำดับก่อนใช้งาน /portal อื่นได้
 * spec: docs/superpowers/specs/2026-07-30-portal-onboarding-flow-design.md
 */
import { redirect } from 'next/navigation';
import { getCustomerByLineId, type Customer } from './customers';
import { parsePortalNotes } from './portal-data';

export function nextOnboardingPath(customer: Customer | null): string | null {
  const notes = parsePortalNotes(customer?.notes ?? '');

  if (!notes.userName?.trim() || !notes.userGmail?.trim()
    || !notes.userPhone?.trim() || !notes.userLineId?.trim()) {
    return '/portal/profile';
  }
  if (!notes.settingsConfirmedAt) {
    return '/portal/settings';
  }
  if (!customer?.has_push_subscription && !notes.notificationsPromptDismissedAt) {
    return '/portal/notifications';
  }
  return null;
}

/** เรียกจากหน้าใช้งานทั่วไป (world, jobs, ...) — fetch customer แล้ว redirect ถ้ายังไม่ผ่าน onboarding */
export async function requireOnboarding(lineUserId: string): Promise<Customer | null> {
  let customer: Customer | null = null;
  try {
    customer = await getCustomerByLineId(lineUserId);
  } catch {
    return null; // engine ล่ม — fail-open ปล่อยเข้า (ไม่ให้ onboarding gate เป็นจุดเดียวที่พังแล้วเข้าไม่ได้เลย)
  }
  const next = nextOnboardingPath(customer);
  if (next) redirect(next);
  return customer;
}
```

- [ ] **Step 4: type check**

Run: `cd dashboard/web && npm run build`
Expected: build ผ่าน ไม่มี TypeScript error (ยังไม่มีใครเรียกใช้ `onboarding.ts` จริง แต่ต้อง compile ผ่าน)

- [ ] **Step 5: Commit**

```bash
git add dashboard/web/src/lib/customers.ts dashboard/web/src/lib/portal-data.ts dashboard/web/src/lib/onboarding.ts
git commit -m "feat(portal): lib/onboarding.ts + types สำหรับ onboarding gate"
```

---

### Task 3: แก้บั๊ก Profile save ล้าง notes + wire onboarding

**Files:**
- Modify: `dashboard/web/src/app/portal/profile/page.tsx`
- Modify: `dashboard/web/src/app/portal/profile/_client.tsx`

**Interfaces:**
- Consumes: `nextOnboardingPath` (Task 2), `PortalNotes` (Task 2)
- Produces: `ProfileClient` prop `notes: PortalNotes`, `isOnboarding: boolean` — ปุ่ม save เปลี่ยนพฤติกรรมตาม flag นี้

- [ ] **Step 1: แก้ `profile/page.tsx`**

เพิ่ม import และ 2 บรรทัดหลังคำนวณ `notes` (บรรทัด ~21 เดิม `const notes = parsePortalNotes(customer?.notes ?? '');`):

```typescript
import { nextOnboardingPath } from '@/lib/onboarding';
// ...
const notes = parsePortalNotes(customer?.notes ?? '');
const nextStep = nextOnboardingPath(customer);
const isOnboarding = nextStep === '/portal/profile';
```

แล้วเพิ่ม 2 prop `notes` และ `isOnboarding` ให้ `<ProfileClient>` (ส่วนอื่นของ JSX เดิมทั้งหมดคงไว้ ไม่แก้):

```typescript
    <ProfileClient
      lineUserId={session.lineUserId}
      notes={notes}
      isOnboarding={isOnboarding}
      initialProfile={{
        companyName: customer?.display_name || session.displayName || '',
        phone: customer?.phone || '',
        email: customer?.email || '',
        budgetMin: notes.budgetMin ?? 1,
        budgetMax: notes.budgetMax ?? 50,
        isSME: notes.isSME ?? false,
        isMIT: notes.isMIT ?? false,
        notifyTime: notes.notifyTime ?? '23:00',
        userName: notes.userName,
        userGmail: notes.userGmail,
        userPhone: notes.userPhone,
        userLineId: notes.userLineId,
      }}
      classes={(notes.classes ?? []).filter(c => c.id !== 'settings')}
      classCount={(notes.classes ?? []).filter(c => c.id !== 'settings').length}
      registeredAt={customer?.registered_at?.slice(0, 10) ?? ''}
      tierId={getTierId(customer ?? { status: 'trial', notes: '' })}
      daysLeft={daysLeft}
      expiryLabel={expiryLabel}
    />
```

- [ ] **Step 2: แก้ `profile/_client.tsx` — merge notes + onboarding button**

แก้ `Props` interface (เพิ่ม 2 ฟิลด์):

```typescript
interface Props {
  lineUserId: string;
  notes: PortalNotes;
  isOnboarding: boolean;
  initialProfile: PortalProfile;
  classes: BusinessClass[];
  classCount: number;
  registeredAt: string;
  tierId: string;
  daysLeft?: number;
  expiryLabel?: string;
}
```

เพิ่ม import `PortalNotes` ในบรรทัด import type เดิม:

```typescript
import type { PortalProfile, PortalNotes, BusinessClass } from '@/lib/portal-data';
```

แก้ function signature รับ `notes`, `isOnboarding`:

```typescript
export function ProfileClient({
  lineUserId,
  notes,
  isOnboarding,
  initialProfile,
  classes,
  classCount,
  registeredAt,
  tierId,
  daysLeft = 30,
  expiryLabel = '',
}: Props) {
```

แก้ `handleSave` (merge `...notes` + onboarding navigation แทน stay-in-place):

```typescript
  const router = useRouter();
  const canSubmit = !isOnboarding || (
    profile.userName?.trim() && profile.userGmail?.trim()
    && profile.userPhone?.trim() && profile.userLineId?.trim()
  );

  const handleSave = async () => {
    if (!canSubmit) return;
    setSaving(true);
    try {
      await fetch('/api/portal/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...notes,
          userName: profile.userName,
          userGmail: profile.userGmail,
          userPhone: profile.userPhone,
          userLineId: profile.userLineId,
        }),
      });
      await fetch(`/api/line/customer?lineUserId=${lineUserId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: profile.companyName, phone: profile.phone, email: profile.email }),
      });
      if (isOnboarding) {
        router.push('/portal/settings');
        return;
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };
```

(`useRouter`/`useState` import อยู่แล้วบนสุดของไฟล์ — ไม่ต้องเพิ่ม import ใหม่)

แก้ปุ่ม save (label + disabled ตาม `canSubmit`):

```tsx
        <button
          className="p-btn p-btn-primary"
          onClick={handleSave}
          disabled={saving || !canSubmit}
          style={{ width: '100%', height: 44, fontSize: 14, marginTop: 4, marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
        >
          {saved ? <><Icons.Check2 size={16} />บันทึกเสร็จแล้ว</>
            : saving ? 'กำลังบันทึก…'
            : isOnboarding ? <><Icons.Check size={16} />บันทึกและดำเนินการต่อ</>
            : <><Icons.Check size={16} />บันทึกข้อมูลส่วนตัว</>}
        </button>
```

เพิ่ม banner อธิบายตอน onboarding เหนือฟอร์ม (ต่อจาก `<ButlerNote>` เดิมที่บรรทัด ~178):

```tsx
        {isOnboarding && (
          <ButlerNote>กรุณากรอกข้อมูลส่วนตัวให้ครบก่อนเริ่มใช้งานนะครับท่าน — ใช้เวลาไม่ถึงนาที</ButlerNote>
        )}
```

- [ ] **Step 3: build**

Run: `cd dashboard/web && npm run build`
Expected: build ผ่าน ไม่มี TypeScript error

- [ ] **Step 4: manual regression check (dev)**

Run: `cd dashboard/web && npm run dev` → login ด้วยบัญชีที่มี `notes.classes`/keyword ตั้งไว้แล้ว (หรือ seed ด้วยมือผ่าน `/portal/settings` ก่อน) → ไปหน้า `/portal/profile` → แก้ชื่อ/เบอร์ → กดบันทึก → เช็คใน DB (`sqlite3 data/bms_customers.db "SELECT notes FROM customers WHERE line_user_id='...'"`) ว่า `classes`/`isSME`/`isMIT`/`notifyTime` ยังอยู่ครบ ไม่หาย

- [ ] **Step 5: Commit**

```bash
git add dashboard/web/src/app/portal/profile/page.tsx dashboard/web/src/app/portal/profile/_client.tsx
git commit -m "fix(portal): profile save ไม่ล้าง notes เดิม + wire onboarding gate ขั้น 1"
```

---

### Task 4: Wire onboarding เข้า Settings page

**Files:**
- Modify: `dashboard/web/src/app/portal/settings/page.tsx`
- Modify: `dashboard/web/src/app/portal/settings/_client.tsx`

**Interfaces:**
- Consumes: `nextOnboardingPath` (Task 2)
- Produces: `settingsConfirmedAt` เขียนลง notes ทุกครั้งที่ save — Task 2's `nextOnboardingPath` อ่านฟิลด์นี้ตรงๆ

- [ ] **Step 1: แก้ `settings/page.tsx`**

เพิ่ม import และเช็คลำดับหลังคำนวณ `notes` (บรรทัด ~22 เดิม):

```typescript
import { nextOnboardingPath } from '@/lib/onboarding';
// ...
const notes = parsePortalNotes(customer?.notes ?? '');
const nextStep = nextOnboardingPath(customer);
if (nextStep === '/portal/profile') redirect('/portal/profile'); // ยังกรอกโปรไฟล์ไม่ครบ ห้ามข้ามมาตั้งค่า
const isOnboarding = nextStep === '/portal/settings';
```

ส่ง prop `isOnboarding` เพิ่มให้ `<SettingsClient>`:

```typescript
  return (
    <SettingsClient
      isOnboarding={isOnboarding}
      provinces={customer?.provinces ?? []}
      initialKeywords={keywords}
      initialBudgetMin={cls?.budgetMinBaht ?? 0}
      initialBudgetMax={cls?.budgetMaxBaht ?? 0}
      initialIsSME={notes.isSME ?? false}
      initialIsMIT={notes.isMIT ?? false}
      initialNotifyTime={notes.notifyTime ?? '23:00'}
      initialMorningTime={notes.morningNotifyTime ?? '07:30'}
      notes={notes}
    />
  );
```

- [ ] **Step 2: แก้ `settings/_client.tsx`**

เพิ่ม `isOnboarding: boolean;` ใน props type และ destructure:

```typescript
export function SettingsClient({ isOnboarding, provinces, initialKeywords, initialBudgetMin, initialBudgetMax, initialIsSME, initialIsMIT, initialNotifyTime, initialMorningTime, notes }: {
  isOnboarding: boolean;
  provinces: string[];
  initialKeywords: string[];
  initialBudgetMin: number;
  initialBudgetMax: number;
  initialIsSME: boolean;
  initialIsMIT: boolean;
  initialNotifyTime: string;
  initialMorningTime: string;
  notes: PortalNotes;
}) {
```

แก้ `save()` — เพิ่ม `settingsConfirmedAt` + onboarding navigation:

```typescript
  const save = async () => {
    setSaving(true); setError(''); setSaved(false);
    try {
      const body: PortalNotes = {
        ...notes,
        classes: toClasses(keywords, budgetMin, budgetMax),
        isSME, isMIT, notifyTime,
        morningNotifyTime: morningTime,
        settingsConfirmedAt: new Date().toISOString(),
      };
      const r = await fetch('/api/portal/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error('save failed');
      if (isOnboarding) {
        router.push('/portal/notifications');
        return;
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2200);
    } catch {
      setError('บันทึกไม่สำเร็จ — ลองใหม่อีกครั้งครับ');
    } finally {
      setSaving(false);
    }
  };
```

แก้ปุ่ม save label:

```tsx
        <button className="p-btn p-btn-primary" onClick={save} disabled={saving}
          style={{ width: '100%', height: 48, fontSize: 15, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          {saved ? <><Icons.Check size={16} />บันทึกเสร็จแล้ว</>
            : saving ? 'กำลังบันทึก…'
            : isOnboarding ? <><Icons.Check size={16} />บันทึกและดำเนินการต่อ</>
            : <><Icons.Check size={16} />บันทึกการตั้งค่า</>}
        </button>
```

เพิ่ม banner ตอน onboarding เหนือการ์ดแรก (ก่อน "📍 พื้นที่ครอบคลุม"):

```tsx
        {isOnboarding && (
          <ButlerNote>ตั้งค่าคร่าวๆ ก่อนได้ครับ — ไม่ใส่อะไรเลยก็ได้ (แปลว่ารับแจ้งเตือนทุกงานในจังหวัดที่ท่านสมัคร) แก้ทีหลังได้เสมอ</ButlerNote>
        )}
```

- [ ] **Step 3: build + manual check**

Run: `cd dashboard/web && npm run build`
Expected: build ผ่าน

Manual (dev): เข้า `/portal/settings` ด้วยบัญชีที่ผ่าน Task 3 แล้วแต่ยังไม่เคยกด "บันทึกการตั้งค่า" → เห็นปุ่ม "บันทึกและดำเนินการต่อ" → กด (ไม่แก้อะไร) → ต้องเด้งไป `/portal/notifications` (หน้ายังไม่มีจนกว่า Task 5 เสร็จ — 404 ชั่วคราวถือว่า pass ขั้นนี้)

- [ ] **Step 4: Commit**

```bash
git add dashboard/web/src/app/portal/settings/page.tsx dashboard/web/src/app/portal/settings/_client.tsx
git commit -m "feat(portal): wire onboarding gate ขั้น 2 (settingsConfirmedAt) เข้าหน้าตั้งค่า"
```

---

### Task 5: หน้า `/portal/notifications` ใหม่

**Files:**
- Create: `dashboard/web/src/app/portal/notifications/page.tsx`
- Create: `dashboard/web/src/app/portal/notifications/_client.tsx`

**Interfaces:**
- Consumes: `nextOnboardingPath` (Task 2), endpoint `/api/portal/push/subscribe` (มีอยู่แล้ว, ดู `dashboard/web/src/app/api/portal/push/subscribe/route.ts`), `/api/portal/save` (merge pattern เดียวกับ Task 3/4)
- Produces: หน้า onboarding ขั้นสุดท้าย — เขียน `notes.notificationsPromptDismissedAt` เมื่อกด "ข้ามไปก่อน"

- [ ] **Step 1: สร้าง `page.tsx`**

```tsx
// dashboard/web/src/app/portal/notifications/page.tsx
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getCustomerByLineId } from '@/lib/customers';
import { parsePortalNotes } from '@/lib/portal-data';
import { nextOnboardingPath } from '@/lib/onboarding';
import { NotificationsClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function NotificationsPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  let customer = null;
  try { customer = await getCustomerByLineId(session.lineUserId); } catch { /* engine unavailable */ }

  const notes = parsePortalNotes(customer?.notes ?? '');
  const nextStep = nextOnboardingPath(customer);
  // ยังไม่ผ่านโปรไฟล์/ตั้งค่า ห้ามข้ามมาหน้านี้ — ผ่านครบแล้ว (nextStep=null) ก็ยังเข้าดูซ้ำได้ (ไม่ใช่ onboarding แล้ว)
  if (nextStep === '/portal/profile' || nextStep === '/portal/settings') redirect(nextStep);

  return <NotificationsClient notes={notes} />;
}
```

- [ ] **Step 2: สร้าง `_client.tsx`**

```tsx
// dashboard/web/src/app/portal/notifications/_client.tsx
'use client';
/**
 * ขั้นตอนสุดท้ายของ onboarding — ขอ permission web push จริง หรือกด "ข้ามไปก่อน"
 * โค้ดขอ permission/subscribe เหมือน PushNotifyCard.tsx (การ์ดเดิมในหน้า world ที่ทำหน้าที่
 * เป็นตัวเตือนถ้าข้าม/ปฏิเสธตรงนี้) — spec: 2026-07-30-portal-onboarding-flow-design.md
 */
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { TopBar, Icons, ButlerNote } from '../_ui';
import type { PortalNotes } from '@/lib/portal-data';

const VAPID_PUBLIC = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? '';

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

type State = 'loading' | 'unsupported' | 'ios-install' | 'off' | 'on' | 'denied';

export function NotificationsClient({ notes }: { notes: PortalNotes }) {
  const router = useRouter();
  const [state, setState] = useState<State>('loading');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    (async () => {
      if (!('serviceWorker' in navigator) || !('PushManager' in window) || !VAPID_PUBLIC) {
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        const standalone = window.matchMedia('(display-mode: standalone)').matches
          || (navigator as unknown as { standalone?: boolean }).standalone === true;
        setState(isIOS && !standalone ? 'ios-install' : 'unsupported');
        return;
      }
      if (Notification.permission === 'denied') { setState('denied'); return; }
      const reg = await navigator.serviceWorker.register('/sw.js');
      const sub = await reg.pushManager.getSubscription();
      setState(sub ? 'on' : 'off');
    })().catch(() => setState('unsupported'));
  }, []);

  const goToBoard = useCallback(() => router.push('/portal/world'), [router]);

  const skip = useCallback(async () => {
    setBusy(true);
    try {
      await fetch('/api/portal/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...notes, notificationsPromptDismissedAt: new Date().toISOString() }),
      });
    } finally {
      setBusy(false);
      goToBoard();
    }
  }, [notes, goToBoard]);

  const enable = useCallback(async () => {
    setBusy(true); setMsg('');
    try {
      const perm = await Notification.requestPermission();
      if (perm !== 'granted') { setState(perm === 'denied' ? 'denied' : 'off'); return; }
      const reg = await navigator.serviceWorker.register('/sw.js');
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC) as BufferSource,
      });
      const json = sub.toJSON();
      const r = await fetch('/api/portal/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: sub.endpoint,
          p256dh: json.keys?.p256dh ?? '',
          auth: json.keys?.auth ?? '',
          user_agent: navigator.userAgent,
        }),
      });
      if (r.status === 403) {
        await sub.unsubscribe();
        setState('off'); setMsg('ฟีเจอร์นี้ยังเปิดทดลองเฉพาะบางบัญชี — กดข้ามไปก่อนได้ครับ');
        return;
      }
      if (!(await r.json()).ok) throw new Error('save failed');
      setState('on');
      goToBoard();
    } catch {
      setMsg('เปิดไม่สำเร็จ ลองใหม่อีกครั้ง หรือกด "ข้ามไปก่อน" แล้วเปิดทีหลังได้');
    } finally { setBusy(false); }
  }, [goToBoard]);

  if (state === 'loading') return null;

  return (
    <div className="p-enter">
      <TopBar title="เปิดการแจ้งเตือน" subtitle="ขั้นตอนสุดท้าย · Sebastian" />
      <div className="p-page p-page-topbar" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <ButlerNote>
          เปิดรับแจ้งเตือนบนเบราว์เซอร์เครื่องนี้ไว้ครับ Sebastian จะได้แจ้งงานประมูลใหม่ให้ทันทีที่เจอ
        </ButlerNote>

        <div className="p-card" style={{ padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent)', marginBottom: 8 }}>
            <Icons.Bell size={18} />
            <span className="p-display" style={{ fontSize: 16 }}>แจ้งเตือนผ่านเบราว์เซอร์</span>
          </div>

          {state === 'ios-install' && (
            <p className="p-fg-mute" style={{ fontSize: 13, lineHeight: 1.6 }}>
              iPhone/iPad: กดปุ่มแชร์ แล้วเลือก &quot;เพิ่มไปยังหน้าจอโฮม&quot; ก่อน
              จากนั้นเปิดจากไอคอนบนหน้าจอโฮมเพื่อเปิดรับแจ้งเตือน — กด &quot;ข้ามไปก่อน&quot; ได้ถ้ายังไม่สะดวก
            </p>
          )}
          {state === 'denied' && (
            <p className="p-fg-mute" style={{ fontSize: 13, lineHeight: 1.6 }}>
              เบราว์เซอร์นี้ถูกตั้งค่าบล็อกแจ้งเตือนไว้ — ไปที่ตั้งค่าเว็บไซต์ของเบราว์เซอร์แล้วอนุญาต
              จากนั้นรีเฟรชหน้านี้ หรือกด &quot;ข้ามไปก่อน&quot; แล้วเปิดทีหลังได้
            </p>
          )}
          {state === 'unsupported' && (
            <p className="p-fg-mute" style={{ fontSize: 13, lineHeight: 1.6 }}>
              เบราว์เซอร์นี้ยังไม่รองรับแจ้งเตือนแบบ push — กด &quot;ข้ามไปก่อน&quot; ได้เลยครับ
            </p>
          )}
          {state === 'on' && (
            <p className="p-fg-mute" style={{ fontSize: 13 }}>✅ เครื่องนี้เปิดรับแจ้งเตือนอยู่แล้ว</p>
          )}

          {state === 'off' && (
            <button className="p-btn p-btn-primary" onClick={enable} disabled={busy}
              style={{ width: '100%', height: 44, marginTop: 10 }}>
              {busy ? 'กำลังเปิด…' : 'เปิดการแจ้งเตือน'}
            </button>
          )}
          {msg && <p className="p-fg-dim" style={{ fontSize: 12.5, marginTop: 8 }}>{msg}</p>}
        </div>

        {state === 'on' ? (
          <button className="p-btn p-btn-primary" onClick={goToBoard} style={{ width: '100%', height: 44 }}>
            เข้าใช้งานบอร์ด
          </button>
        ) : (
          <button className="p-btn p-btn-ghost" onClick={skip} disabled={busy} style={{ width: '100%', height: 44 }}>
            ข้ามไปก่อน
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: build**

Run: `cd dashboard/web && npm run build`
Expected: build ผ่าน ไม่มี TypeScript error

- [ ] **Step 4: manual check (dev)**

Run: `npm run dev` → เข้า `/portal/settings` ด้วยบัญชีที่ผ่าน Task 3 (โปรไฟล์ครบ) แต่ยังไม่เคยกดบันทึกตั้งค่า → กด "บันทึกและดำเนินการต่อ" → ต้องเด้งเข้า `/portal/notifications` จริง → กด "เปิดการแจ้งเตือน" → Chrome ขอ permission → อนุญาต → เด้งเข้า `/portal/world` เอง; ทดสอบอีกรอบด้วยบัญชี/browser profile ใหม่ที่ยัง onboarding ไม่ครบ → กด "ข้ามไปก่อน" → เด้งเข้า `/portal/world` เหมือนกัน → เช็ค DB ว่า `notes.notificationsPromptDismissedAt` มีค่า และ `notes.classes`/keyword เดิม (ถ้ามี) ไม่หาย

- [ ] **Step 5: Commit**

```bash
git add "dashboard/web/src/app/portal/notifications"
git commit -m "feat(portal): หน้า /portal/notifications — onboarding gate ขั้น 3 (เปิด/ข้ามแจ้งเตือน)"
```

---

### Task 6: บังคับ gate ในหน้าใช้งานทั่วไป (8 หน้า)

**Files:**
- Modify: `dashboard/web/src/app/portal/world/page.tsx`
- Modify: `dashboard/web/src/app/portal/jobs/page.tsx`
- Modify: `dashboard/web/src/app/portal/history/page.tsx`
- Modify: `dashboard/web/src/app/portal/packages/page.tsx`
- Modify: `dashboard/web/src/app/portal/documents/page.tsx`
- Modify: `dashboard/web/src/app/portal/company-stats/page.tsx`
- Modify: `dashboard/web/src/app/portal/job/[pid]/page.tsx`
- Modify: `dashboard/web/src/app/portal/company/[tin]/page.tsx`

**Interfaces:**
- Consumes: `requireOnboarding` (Task 2)

- [ ] **Step 1: `world/page.tsx` — สลับมาใช้ `requireOnboarding` แทนการ fetch ตรง**

แก้ import (ตัด `getCustomerByLineId`, เพิ่ม `requireOnboarding`):

```typescript
import { requireOnboarding } from '@/lib/onboarding';
```

แก้บล็อกนี้ (บรรทัด ~20-23 เดิม):

```typescript
  let customer = null;
  try {
    customer = await getCustomerByLineId(session.lineUserId);
  } catch { /* Sheets unavailable — use defaults */ }
```

เป็น:

```typescript
  const customer = await requireOnboarding(session.lineUserId);
```

- [ ] **Step 2: `jobs/page.tsx` — เพิ่ม gate call (ไม่เคยมี customer fetch มาก่อน)**

เพิ่ม import:

```typescript
import { requireOnboarding } from '@/lib/onboarding';
```

เพิ่มบรรทัดหลัง session check (หลัง `if (!session) redirect('/portal/login');`):

```typescript
  await requireOnboarding(session.lineUserId);
```

- [ ] **Step 3: `history/page.tsx` — เพิ่ม gate call**

เพิ่ม import:

```typescript
import { requireOnboarding } from '@/lib/onboarding';
```

เพิ่มบรรทัดหลัง session check (หลัง `if (!session) redirect('/portal/login');`):

```typescript
  await requireOnboarding(session.lineUserId);
```

- [ ] **Step 4: `packages/page.tsx` — สลับมาใช้ `requireOnboarding`**

แก้ import (ตัด `getCustomerByLineId`, เพิ่ม `requireOnboarding`) แก้บรรทัด (~18-19 เดิม):

```typescript
  let customer = null;
  try { customer = await getCustomerByLineId(session.lineUserId); } catch { /* ignore */ }
```

เป็น:

```typescript
  const customer = await requireOnboarding(session.lineUserId);
```

- [ ] **Step 5: `documents/page.tsx` — สลับมาใช้ `requireOnboarding`**

แก้ import (ตัด `getCustomerByLineId`, เพิ่ม `requireOnboarding`):

```typescript
import { requireOnboarding } from '@/lib/onboarding';
```

แก้บล็อกนี้ (บรรทัด ~18-19 เดิม):

```typescript
  let customer = null;
  try { customer = await getCustomerByLineId(session.lineUserId); } catch { /* ignore */ }
```

เป็น:

```typescript
  const customer = await requireOnboarding(session.lineUserId);
```

- [ ] **Step 6: `company-stats/page.tsx` — สลับมาใช้ `requireOnboarding`**

แก้ import (ตัด `getCustomerByLineId`, เพิ่ม `requireOnboarding`):

```typescript
import { requireOnboarding } from '@/lib/onboarding';
```

แก้บล็อกนี้ (บรรทัด ~22-23 เดิม):

```typescript
  let customer = null;
  try { customer = await getCustomerByLineId(session.lineUserId); } catch { /* ignore */ }
```

เป็น:

```typescript
  const customer = await requireOnboarding(session.lineUserId);
```

- [ ] **Step 7: `job/[pid]/page.tsx` — เพิ่ม gate call**

เพิ่ม import:

```typescript
import { requireOnboarding } from '@/lib/onboarding';
```

เพิ่มบรรทัดหลัง session check และก่อน `const { pid } = await params;`:

```typescript
  await requireOnboarding(session.lineUserId);
```

- [ ] **Step 8: `company/[tin]/page.tsx` — เพิ่ม gate call**

เพิ่ม import:

```typescript
import { requireOnboarding } from '@/lib/onboarding';
```

เพิ่มบรรทัดหลัง session check และก่อน `const { tin } = await params;`:

```typescript
  await requireOnboarding(session.lineUserId);
```

- [ ] **Step 9: build**

Run: `cd dashboard/web && npm run build`
Expected: build ผ่าน ไม่มี TypeScript error, ไม่มี unused-import warning (เช่น `getCustomerByLineId` ที่ตัดออกจาก world/packages/documents/company-stats แต่ไม่มีจุดอื่นในไฟล์เดียวกันใช้แล้ว)

- [ ] **Step 10: Commit**

```bash
git add dashboard/web/src/app/portal/world/page.tsx dashboard/web/src/app/portal/jobs/page.tsx \
  dashboard/web/src/app/portal/history/page.tsx dashboard/web/src/app/portal/packages/page.tsx \
  dashboard/web/src/app/portal/documents/page.tsx dashboard/web/src/app/portal/company-stats/page.tsx \
  "dashboard/web/src/app/portal/job/[pid]/page.tsx" "dashboard/web/src/app/portal/company/[tin]/page.tsx"
git commit -m "feat(portal): บังคับ onboarding gate ในหน้าใช้งานทั่วไปทั้งหมด"
```

---

### Task 7: Manual E2E ทั้ง flow (dev, local)

**Files:** ไม่มีไฟล์แก้ (verification-only — ถ้าเจอบั๊กระหว่างนี้ กลับไปแก้ Task ที่เกี่ยวก่อน แล้วรัน Task 7 ใหม่)

- [ ] **Step 1: เตรียมบัญชีทดสอบใหม่**

ลบ/เปลี่ยนแถว test customer ใน local DB (`data/bms_customers.db`) ให้เหมือนบัญชีที่เพิ่ง login ครั้งแรก (notes ว่าง, ไม่มี push_subscriptions) — หรือสร้าง LINE test user ใหม่ถ้ามี dev channel

- [ ] **Step 2: รัน dev server**

Run: `cd dashboard/web && npm run dev`
Expected: server ขึ้นที่ `http://localhost:3000`

- [ ] **Step 3: เดิน flow เต็ม**

1. Login ด้วยบัญชีทดสอบ → ต้องเจอ `/portal/profile` (ไม่ใช่ `/portal/world`) ✅
2. พิมพ์ URL `/portal/world` ตรงๆ ระหว่างที่ยังไม่กรอกโปรไฟล์ → ต้องเด้งกลับ `/portal/profile` ✅
3. กรอกโปรไฟล์ไม่ครบ (เว้น LINE ID ว่าง) → ปุ่มต้อง disabled ✅
4. กรอกครบ 4 ช่อง → กด "บันทึกและดำเนินการต่อ" → เด้งไป `/portal/settings` ✅
5. ที่ `/portal/settings` ไม่แก้อะไร กด "บันทึกและดำเนินการต่อ" → เด้งไป `/portal/notifications` ✅ (แม้ไม่มีจังหวัด ไม่ค้าง)
6. ที่ `/portal/notifications` กด "ข้ามไปก่อน" → เด้งไป `/portal/world` ✅ → เห็นการ์ด `PushNotifyCard` ในหน้า world เตือนให้เปิดทีหลัง ✅
7. Refresh `/portal/profile` และ `/portal/settings` อีกครั้ง (onboarding ผ่านครบแล้ว) → ปุ่มต้องกลับเป็น label ปกติ ("บันทึกข้อมูลส่วนตัว" / "บันทึกการตั้งค่า") ไม่ forced-navigate อีก ✅

- [ ] **Step 4: ทดสอบ path เปิดแจ้งเตือนจริง**

ทำซ้ำ Step 3 ด้วยบัญชีทดสอบอีกตัว แต่ที่ขั้น notifications กด "เปิดการแจ้งเตือน" แทน → เบราว์เซอร์ต้องขึ้น permission popup จริง → กด Allow → ต้องเด้งเข้า `/portal/world` เอง (ไม่ใช่ค้างอยู่หน้าเดิม) → เช็ค `data/bms_customers.db` ว่ามีแถวใน `push_subscriptions` ของบัญชีนี้ (`disabled_at IS NULL`)

- [ ] **Step 5: ทดสอบ regression บั๊ก merge-notes**

ใช้บัญชีที่ Step 3-4 ผ่านแล้ว (มี `notes.classes` จาก settings) → ไปหน้า `/portal/profile` → แก้เบอร์โทร → บันทึก (ปุ่มปกติแล้ว) → เช็ค `notes.classes` ยังอยู่ ไม่หาย

- [ ] **Step 6: บันทึกผลใน progress_log**

ถ้าทุกข้อผ่าน → บันทึก checklist นี้ (ผ่าน/ไม่ผ่านแต่ละข้อ) ไว้ใน `progress_log.md` (จะรวมเป็น entry เดียวกับ Task 8) ถ้ามีข้อไหนไม่ผ่าน → กลับไปแก้ Task ที่เกี่ยวก่อน ห้ามข้ามไป Task 8

---

### Task 8: Deploy + เปิด PUSH_ALLOWLIST ให้ทุกบัญชี + progress_log + sanity

**Files:**
- Modify: `progress_log.md` (entry ใหม่)
- Vercel project env (`PUSH_ALLOWLIST`) — ไม่ใช่ไฟล์ในโค้ด
- VPS `/opt/bms/app` — ต้อง `git pull` + restart `bms-api` แยกจาก Vercel (Task 1 แก้ `scripts/bms_api.py`)

**Interfaces:**
- Consumes: ทุก Task ก่อนหน้า commit ครบแล้วบน local `main`, Task 7 ผ่านครบ

- [ ] **Step 1: 🛑 GATE — ขอ confirm คุณกัญจน์ก่อน push origin + deploy** (กฎ CLAUDE.md ห้าม push โดยไม่ confirm)

- [ ] **Step 2: push + deploy บอร์ด (Vercel)**

```bash
git push origin main
```

Deploy ตาม flow เดิมของ repo (`cd dashboard/web && npx vercel --prod` หรือ auto-deploy จาก push ถ้า project ผูก GitHub อยู่แล้ว)
Expected: deploy READY, `/portal/profile` ขึ้นจริงบน production

- [ ] **Step 2.5: Deploy backend (VPS) — Task 1 แก้ `scripts/bms_api.py`, ต้อง deploy แยกจาก Vercel**

**เพิ่มหลัง final whole-branch review พบว่าขาดขั้นนี้ (2026-07-30):** Vercel deploy ไม่แตะ backend เลย ถ้าข้ามขั้นนี้ `GET /api/portal/customer` จะยังไม่มี `has_push_subscription` ในผล → `toCustomer()` fallback เป็น `false` เสมอ (`dashboard/web/src/lib/customers.ts:65`) → ลูกค้าที่เปิดแจ้งเตือนไปแล้วจะถูกเด้งกลับไปหน้า `/portal/notifications` ซ้ำไม่รู้จบ โดยไม่มี error ให้เห็น

```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "cd /opt/bms/app && bash scripts/deploy.sh"
```

Expected: `git pull --ff-only` สำเร็จ, `bms-api` service `active`

Sanity check ทันที (ก่อนไป Step 3):
```bash
ssh -i ~/.ssh/bms_vps root@45.76.156.166 "curl -s -H 'X-BMS-Secret: <BMS_INTERNAL_SECRET>' 'http://localhost:8000/api/portal/customer?line_user_id=<line_user_id ของคุณกัญจน์>' | grep -o has_push_subscription"
```
Expected: เจอคำว่า `has_push_subscription` ในผล (ยืนยันว่า field มาจริง ไม่ใช่ fallback `false` เงียบๆ)

- [ ] **Step 3: E2E บน production ด้วยบัญชีคุณกัญจน์ก่อน (ยัง PUSH_ALLOWLIST เดิม)**

เดิน flow เดียวกับ Task 7 Step 3-5 แต่บน `https://bid-master-dashboard.vercel.app` จริง ด้วยบัญชี LINE ของคุณกัญจน์ (ซึ่งจะถูกบังคับผ่าน onboarding ใหม่ตามที่ตกลง — grandfather ไม่ยกเว้น) ✅ ครบทุกข้อ

- [ ] **Step 4: 🛑 GATE — ขอ confirm คุณกัญจน์ก่อนเคลียร์ `PUSH_ALLOWLIST`** (นี่คือขั้นที่ "เปิดให้ทุกคนใช้ได้จริง" — เปลี่ยนพฤติกรรม production ให้บัญชีอื่นที่ไม่ใช่คุณกัญจน์ subscribe web push ได้)

- [ ] **Step 5: เคลียร์ `PUSH_ALLOWLIST` บน Vercel**

Vercel dashboard → Project → Settings → Environment Variables → ลบค่าใน `PUSH_ALLOWLIST` (หรือแก้เป็นค่าว่าง) → Production → Redeploy (หรือ `npx vercel env rm PUSH_ALLOWLIST production` แล้ว deploy ใหม่)
Expected: deploy ใหม่สำเร็จ

- [ ] **Step 6: ยืนยันด้วยบัญชี LINE อื่น (ไม่ใช่คุณกัญจน์)**

Login ด้วยบัญชี LINE ทดสอบอีกตัว (ไม่ใช่ของคุณกัญจน์) → เดิน onboarding จนถึงขั้นกด "เปิดการแจ้งเตือน" → ต้อง**ไม่**เจอ error 403 "ฟีเจอร์นี้ยังเปิดทดลองเฉพาะบางบัญชี" อีกต่อไป → subscribe สำเร็จจริง

- [ ] **Step 7: Sanity check (กฎ CLAUDE.md — dispatch Sophia ถ้า available, ไม่งั้นรันเอง)**

- `notes` column ของบัญชีทดสอบใน Task 7/8 ไม่มีแถวไหนถูก JSON คนละก้อนทับกัน (เทียบ `classes`/`isSME`/`userName` ยังอยู่ครบตามลำดับขั้นที่ทำ)
- `SELECT COUNT(*) FROM customers WHERE notes IS NOT NULL AND notes != '' AND notes NOT LIKE '{%'` → ต้องเป็น 0 (notes ทุกแถวยังเป็น JSON object ที่ valid)
- ไม่มี exception ใหม่ใน Vercel function log ช่วง 10 นาทีแรกหลัง deploy

- [ ] **Step 8: progress_log entry + commit + Discord**

เพิ่ม entry ใหม่ใน `progress_log.md` (ชื่องาน: "Portal onboarding flow (profile→settings→เปิดแจ้งเตือน) LIVE", สถานะ ✅ เสร็จ, สรุปผล Task 7/8 checklist, ผลลัพธ์ `PUSH_ALLOWLIST` เปิดแล้ว) → commit:

```bash
git add progress_log.md
git commit -m "docs(progress): portal onboarding flow LIVE — PUSH_ALLOWLIST เปิดทุกบัญชี"
git push origin main
```

Discord notify: "✅ Portal onboarding flow (profile→settings→เปิดแจ้งเตือน) LIVE — เปิด Web Push ให้ทุกบัญชีแล้ว"
