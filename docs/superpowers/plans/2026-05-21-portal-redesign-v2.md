# Portal Redesign v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ปรับปรุง 10 จุดในหน้า Customer Portal — discount stats, bottom nav, เปลี่ยนชื่อ BusinessClass → บริษัท, mini-map จริง, keyword defaults, per-company filter settings, profile redesign, star jobs, own-company history, file upload.

**Architecture:** ทุกอย่างอยู่ใน `dashboard/web/src/app/portal/` และ `src/lib/` — ไม่แตะ admin dashboard. State ที่ต้องบันทึกเก็บใน `PortalNotes` JSON → customer.notes (Google Sheets). DB queries เพิ่มใน `src/lib/bid-history.ts` + PostgreSQL materialized view.

**Tech Stack:** Next.js App Router (TypeScript), `@neondatabase/serverless` (PostgreSQL), `leaflet` + `react-leaflet` (OpenStreetMap), `portal.css` design tokens.

---

## File Map

| File | Action | เหตุผล |
|---|---|---|
| `scripts/db_schema.sql` | Modify | เพิ่ม discount_from_budget_pct, stddev ใน competitor_profiles view |
| `src/lib/bid-history.ts` | Modify | เพิ่ม types + query สำหรับ own company bids |
| `src/lib/portal-data.ts` | Modify | เพิ่ม fields ใน BusinessClass, PortalNotes; ขยาย DEFAULT_KEYWORDS |
| `src/app/portal/_shell.tsx` | Modify | เพิ่ม "ประวัติ" ใน bottom nav (5 items) |
| `src/app/portal/history/_client.tsx` | Modify | discount UI + 3-tab layout (งาน/บริษัท/ฉัน) |
| `src/app/portal/classes/_client.tsx` | Modify | rename → บริษัท, keywords as checkboxes, filter tab, บันทึก navigation |
| `src/app/portal/classes/_map-preview.tsx` | Create | Leaflet map component (dynamic import, SSR disabled) |
| `src/app/portal/profile/_client.tsx` | Modify | add LINE ID, account status, expiry display |
| `src/app/portal/world/_client.tsx` | Modify | star/favorite system, งานที่สนใจ section |
| `src/app/api/portal/history/mine/route.ts` | Create | GET /api/portal/history/mine — own company bid history |
| `src/app/api/portal/upload/route.ts` | Create | POST /api/portal/upload — file upload per company |

---

## Task 1: DB — เพิ่ม discount_from_budget_pct ใน competitor_profiles

**Files:**
- Modify: `scripts/db_schema.sql`

แต่ละ bid ใน bid_history มี `price_proposal` กับ `price_agree`; `all_jobs` มี `budget`. Discount จาก budget = `(budget - price_agree) / budget * 100`. เพิ่มค่านี้ใน materialized view.

- [ ] **Step 1: อ่าน materialized view ปัจจุบัน**

```bash
# เพื่อทำความเข้าใจ SQL ที่มีอยู่
head -80 scripts/db_schema.sql
```

- [ ] **Step 2: อัปเดต competitor_profiles view ใน db_schema.sql**

หา block `CREATE MATERIALIZED VIEW competitor_profiles` แล้วแก้ SELECT ให้เพิ่ม 2 column ใหม่:

```sql
-- เพิ่มใน SELECT ของ competitor_profiles view:
,ROUND(AVG(
  CASE WHEN aj.budget > 0 AND bh.price_agree IS NOT NULL AND bh.price_agree::numeric > 0
       THEN (aj.budget::numeric - bh.price_agree::numeric) / aj.budget::numeric * 100
  END
)::numeric, 1) AS avg_discount_from_budget_pct
,ROUND(STDDEV(
  CASE WHEN aj.budget > 0 AND bh.price_agree IS NOT NULL AND bh.price_agree::numeric > 0
       THEN (aj.budget::numeric - bh.price_agree::numeric) / aj.budget::numeric * 100
  END
)::numeric, 1) AS stddev_discount_pct

-- ใน FROM clause ให้ JOIN all_jobs:
-- (ถ้ายังไม่มี) JOIN all_jobs aj ON aj.job_id = bh.job_id
```

- [ ] **Step 3: Refresh materialized view ใน Neon**

```bash
python scripts/etl_sheet_to_db.py --refresh-views
# ถ้าไม่มี flag นี้ให้รัน SQL ตรงๆ:
# REFRESH MATERIALIZED VIEW CONCURRENTLY competitor_profiles;
```

Expected: ไม่มี error; `SELECT avg_discount_from_budget_pct FROM competitor_profiles LIMIT 3;` คืนค่า

- [ ] **Step 4: ตรวจสอบ**

```bash
python -c "
from scripts.bid_history_queries import get_db
db = get_db()
rows = db.execute('SELECT bidder_tin, avg_discount_from_budget_pct, stddev_discount_pct FROM competitor_profiles LIMIT 5').fetchall()
for r in rows: print(r)
"
```

Expected: เห็น float values บาง row (บางบริษัทอาจ NULL ถ้าไม่มี price_agree)

- [ ] **Step 5: Commit**

```bash
git add scripts/db_schema.sql
git commit -m "feat(db): เพิ่ม avg_discount_from_budget_pct + stddev ใน competitor_profiles view"
```

---

## Task 2: History UI — discount display + 3-tab layout

**Files:**
- Modify: `src/lib/bid-history.ts` — เพิ่ม fields ใน CompetitorProfile + new query
- Modify: `src/app/portal/history/_client.tsx` — เพิ่ม discount UI + 3rd tab "บริษัทฉัน"
- Create: `src/app/api/portal/history/mine/route.ts` — GET endpoint

### 2a: เพิ่ม types + own-company query ใน bid-history.ts

- [ ] **Step 1: อัปเดต CompetitorProfile type**

ใน `src/lib/bid-history.ts` เพิ่ม 2 fields ใน interface:

```typescript
export interface CompetitorProfile {
  bidder_tin: string;
  company_name: string;
  total_bids: number;
  total_wins: number;
  win_rate_pct: number;
  is_sme: boolean;
  has_jv: boolean;
  first_seen: string;
  last_seen: string;
  provinces: string[];
  proc_types: string[];
  avg_discount_pct: number | null;
  avg_discount_from_budget_pct: number | null;  // ใหม่
  stddev_discount_pct: number | null;            // ใหม่
}
```

- [ ] **Step 2: อัปเดต SQL ใน queryCompetitorProfile ให้ดึง fields ใหม่**

```typescript
db`SELECT bidder_tin, company_name, total_bids, total_wins, win_rate_pct,
          is_sme, has_jv, first_seen, last_seen, provinces, proc_types,
          avg_discount_pct, avg_discount_from_budget_pct, stddev_discount_pct
   FROM competitor_profiles WHERE bidder_tin = ${tin}`
```

- [ ] **Step 3: เพิ่ม searchOwnBids function**

```typescript
export async function searchOwnBids(companyName: string): Promise<{ jobs: RecentJobRow[]; total: number }> {
  const db = getDb();
  const like = '%' + companyName.replace(/%/g, '\\%') + '%';
  const rows = await db`
    SELECT bh.job_id, aj.title, aj.department, aj.province, aj.publish_date,
           bh.is_winner, bh.price_proposal, bh.price_agree
    FROM bid_history bh
    JOIN all_jobs aj ON aj.job_id = bh.job_id
    WHERE bh.bidder_name ILIKE ${like}
    ORDER BY aj.publish_date DESC
    LIMIT 50
  `;
  return { jobs: rows as RecentJobRow[], total: rows.length };
}
```

### 2b: สร้าง API route สำหรับ own bids

- [ ] **Step 4: สร้างไฟล์ route**

สร้าง `src/app/api/portal/history/mine/route.ts`:

```typescript
import { NextRequest, NextResponse } from 'next/server';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getCustomerByLineId } from '@/lib/customers';
import { searchOwnBids } from '@/lib/bid-history';

export async function GET(req: NextRequest) {
  const sessionValue = req.cookies.get(COOKIE_NAME)?.value;
  if (!sessionValue) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const session = await parseSessionCookie(sessionValue);
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  let companyName = req.nextUrl.searchParams.get('company') ?? '';
  if (!companyName) {
    try {
      const customer = await getCustomerByLineId(session.lineUserId);
      companyName = customer?.display_name ?? '';
    } catch { /* fallback to empty */ }
  }
  if (!companyName) return NextResponse.json({ jobs: [], total: 0 });

  const result = await searchOwnBids(companyName);
  return NextResponse.json(result);
}
```

### 2c: อัปเดต history/_client.tsx

- [ ] **Step 5: เพิ่ม tab "บริษัทฉัน" + state**

แทนที่ tab switcher ปัจจุบัน (job/company) ด้วย 3-tab layout:

```typescript
const [tab, setTab] = useState<'job' | 'company' | 'mine'>('job');
const [mineResult, setMineResult] = useState<{ jobs: RecentJobRow[]; total: number } | null>(null);
```

- [ ] **Step 6: เพิ่ม loadMine function**

```typescript
async function loadMine() {
  setLoading(true); resetState();
  try {
    const res = await fetch('/api/portal/history/mine');
    if (!res.ok) { setError('ไม่พบข้อมูล'); return; }
    const data = await res.json();
    setMineResult(data);
  } catch { setError('เกิดข้อผิดพลาด'); }
  finally { setLoading(false); }
}
```

- [ ] **Step 7: auto-load mine tab เมื่อ switch มา**

```typescript
// ใน tab switcher onClick:
if (t === 'mine' && !mineResult) loadMine();
```

- [ ] **Step 8: อัปเดต tab buttons เป็น 3 ปุ่ม**

```tsx
{(['job', 'company', 'mine'] as const).map(t => (
  <button key={t} onClick={() => { setTab(t); resetState(); if (t === 'mine' && !mineResult) loadMine(); }}
    style={{
      padding: '6px 14px', fontSize: 13, borderRadius: 6, border: '1px solid var(--border)',
      background: tab === t ? 'var(--accent)' : 'var(--surface)',
      color: tab === t ? '#000' : 'inherit', cursor: 'pointer', fontWeight: tab === t ? 600 : 400,
    }}>
    {t === 'job' ? 'ค้นหางาน' : t === 'company' ? 'ค้นหาบริษัท' : '🏢 บริษัทฉัน'}
  </button>
))}
```

- [ ] **Step 9: เพิ่ม discount display ใน ProfileView**

ใน ProfileView ภายใน stats grid (ปัจจุบัน 4 items) เพิ่ม 2 items:

```tsx
['Discount (จากงบ)', p.avg_discount_from_budget_pct != null ? Number(p.avg_discount_from_budget_pct).toFixed(1) : '—', p.avg_discount_from_budget_pct != null ? '%' : ''],
['Stddev', p.stddev_discount_pct != null ? Number(p.stddev_discount_pct).toFixed(1) : '—', p.stddev_discount_pct != null ? '%' : ''],
```

- [ ] **Step 10: เพิ่ม discount ใน BidderCard**

ใน `<div className="p-fg-mute"...>` ใน BidderCard เพิ่ม discount from budget ถ้า job budget ส่งมา:

```typescript
// BidderCard รับ budget จาก jobResult.job.budget
function BidderCard({ b, onProfileClick, jobBudget }: { b: BidderRow; onProfileClick: (tin: string) => void; jobBudget?: string }) {
  const discPct = jobBudget && b.price_agree
    ? ((parseFloat(jobBudget) - parseFloat(b.price_agree)) / parseFloat(jobBudget) * 100)
    : null;
  // ... แสดงผล:
  // {discPct != null && ` · ส่วนลด ${discPct.toFixed(1)}%`}
}
```

ใน JobCard render: `<BidderCard key={i} b={b} onProfileClick={loadProfile} jobBudget={jobResult.job.budget} />`

- [ ] **Step 11: แสดง mine tab results**

```tsx
{tab === 'mine' && mineResult && (
  <div>
    <div className="p-label" style={{ marginBottom: 8 }}>พบ {mineResult.total} งานที่บริษัทเคยเสนอราคา</div>
    {mineResult.jobs.length === 0 && (
      <div className="p-card" style={{ color: 'var(--fg-mute)', fontSize: 13 }}>
        ไม่พบประวัติ — Sebastian จะค้นหาด้วยชื่อบริษัทที่ตั้งค่าไว้ในโปรไฟล์
      </div>
    )}
    {mineResult.jobs.map((j, i) => (
      <div key={i} className="p-card" style={{ marginBottom: 6, cursor: 'pointer',
        borderColor: j.is_winner ? 'var(--accent-deep)' : 'var(--border)' }}
        onClick={() => handleJobClick(j.job_id)}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <span style={{ fontSize: 13, flex: 1 }}>
            {j.title.length > 65 ? j.title.slice(0, 65) + '…' : j.title}
          </span>
          {j.is_winner && <span className="p-chip" style={{ background: 'var(--accent)', color: '#000', fontSize: 10, marginLeft: 6, flexShrink: 0 }}>ชนะ</span>}
        </div>
        <div className="p-fg-mute" style={{ fontSize: 11, marginTop: 2 }}>
          {j.department} · {j.province} · {j.publish_date} · เสนอ {fmt(j.price_proposal)} บาท
        </div>
      </div>
    ))}
  </div>
)}
```

- [ ] **Step 12: Commit**

```bash
git add src/lib/bid-history.ts src/app/api/portal/history/mine/route.ts src/app/portal/history/_client.tsx
git commit -m "feat(history): discount%, 3-tab layout (งาน/บริษัท/ฉัน), own-company bid history"
```

---

## Task 3: เพิ่ม "ประวัติ" ใน global bottom nav

**Files:**
- Modify: `src/app/portal/_shell.tsx`

- [ ] **Step 1: อัปเดต NAV_ITEMS เป็น 5 items**

```typescript
// เพิ่ม History icon
function HistoryIcon({ size = 20, active = false }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={active ? 2 : 1.5} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <polyline points="12 6 12 12 16 14"/>
    </svg>
  );
}

const NAV_ITEMS = [
  { href: '/portal/world',    label: 'หน้าหลัก', Icon: HomeIcon },
  { href: '/portal/classes',  label: 'บริษัท',   Icon: LayersIcon },
  { href: '/portal/history',  label: 'ประวัติ',   Icon: HistoryIcon },
  { href: '/portal/profile',  label: 'โปรไฟล์',  Icon: UserIcon },
  { href: '/portal/packages', label: 'แพ็กเกจ',  Icon: CrownIcon },
];
```

- [ ] **Step 2: ลด font-size label ใน .p-nav-item ให้ 5 items พอดี**

ใน `portal.css` แก้ `.p-nav-item`:
```css
[data-portal] .p-nav-item {
  font-size: 9px;  /* ลดจาก 10px */
}
```

- [ ] **Step 3: Commit**

```bash
git add src/app/portal/_shell.tsx src/app/portal/portal.css
git commit -m "feat(nav): เพิ่ม ประวัติ ใน bottom nav (5 items)"
```

---

## Task 4: Rename Business Class → บริษัท + Keywords เป็น Checkboxes

**Files:**
- Modify: `src/app/portal/classes/_client.tsx`
- Modify: `src/lib/portal-data.ts` — ขยาย DEFAULT_KEYWORDS_BY_CLASS

### 4a: ขยาย keywords defaults

- [ ] **Step 1: อัปเดต DEFAULT_KEYWORDS_BY_CLASS ใน portal-data.ts**

```typescript
export const DEFAULT_KEYWORDS_BY_CLASS: Record<string, string[]> = {
  'คอนกรีตผสมเสร็จ': ['คอนกรีตผสมเสร็จ', 'Ready-mixed Concrete', 'RMC', 'คอนกรีต', 'ปูนซีเมนต์'],
  'ท่ออัดแรง': ['ท่ออัดแรง', 'ท่อคอนกรีตอัดแรง', 'Prestressed Concrete Pipe', 'ท่อระบายน้ำ', 'คสล.'],
  'รับเหมาก่อสร้าง': ['รับเหมาก่อสร้าง', 'ก่อสร้างอาคาร', 'งานโยธา', 'ปรับปรุงอาคาร', 'ต่อเติม'],
  'งานโยธา': ['งานโยธา', 'ก่อสร้างถนน', 'ท่อระบายน้ำ', 'ดิน', 'เกรด', 'ลูกรัง', 'ถนนลาดยาง'],
  'งานไฟฟ้า': ['งานไฟฟ้า', 'ระบบไฟฟ้า', 'ติดตั้งไฟฟ้า', 'สายไฟ', 'ตู้ไฟ', 'หม้อแปลง'],
  'งานเหล็ก': ['งานเหล็ก', 'โครงเหล็ก', 'เหล็กก่อสร้าง', 'เหล็กเส้น', 'เหล็กแผ่น'],
  'งานประปา': ['ประปา', 'ระบบน้ำ', 'ท่อประปา', 'ระบบน้ำดื่ม', 'สูบน้ำ'],
  'งานสะพาน': ['สะพาน', 'คสล.', 'ข้ามคลอง', 'สะพานคอนกรีต', 'รางระบาย'],
  'อุปกรณ์การแพทย์': ['อุปกรณ์การแพทย์', 'เครื่องมือแพทย์', 'Medical Equipment'],
  'คอมพิวเตอร์และ IT': ['คอมพิวเตอร์', 'Server', 'Network', 'Software', 'ระบบสารสนเทศ'],
  'เฟอร์นิเจอร์และครุภัณฑ์': ['เฟอร์นิเจอร์', 'ครุภัณฑ์', 'โต๊ะ', 'เก้าอี้', 'ตู้เอกสาร'],
  'รถยนต์และยานพาหนะ': ['รถยนต์', 'รถบรรทุก', 'ยานพาหนะ', 'รถกระบะ'],
};

export const CLASS_SUGGESTIONS = Object.keys(DEFAULT_KEYWORDS_BY_CLASS);
```

### 4b: Rename UI strings + checkboxes keywords

- [ ] **Step 2: เปลี่ยน TopBar title และ string ทั้งหมดใน classes/_client.tsx**

แก้ทุก occurrence ของ "Business Class" → "บริษัท":
- `TopBar title="Business Class"` → `title="บริษัทของฉัน"`
- `title="BUSINESS CLASS"` → `title="บริษัทของฉัน"`
- `"เพิ่ม Business Class"` → `"เพิ่มบริษัท"`
- `"เพิ่ม Business Class แรก"` → `"เพิ่มบริษัทแรก"`
- `"ชื่อ Business Class"` → `"ชื่อบริษัท"`
- `"ยังไม่มี Business Class"` → `"ยังไม่มีบริษัท"`
- `subtitle={...}` → `subtitle="บริษัทที่ลงทะเบียน"`

- [ ] **Step 3: เปลี่ยน AddClassModal title และ description**

```tsx
<Modal open={open} onClose={onClose} title="เพิ่มบริษัท">
  <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14, marginBottom: 14 }}>
    ระบุชื่อบริษัท — Sebastian จะแนะนำ keywords เริ่มต้นให้
  </div>
  <Field label="ชื่อบริษัท">
    <input ... placeholder="เช่น BSC ทรัพย์คอนกรีต" />
  </Field>
  <div className="p-mono p-fg-dim" style={{ fontSize: 10.5, letterSpacing: '0.08em', marginBottom: 8 }}>ประเภทธุรกิจที่รับ (เลือกได้หลายอย่าง)</div>
  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 18 }}>
    {CLASS_SUGGESTIONS.map(s => (
      <button key={s} onClick={() => setSelectedTypes(prev =>
        prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]
      )} className={selectedTypes.includes(s) ? 'p-chip p-chip-gold' : 'p-chip p-chip-outline'}
        style={{ cursor: 'pointer' }}>
        {selectedTypes.includes(s) && '✓ '}{s}
      </button>
    ))}
  </div>
```

- [ ] **Step 4: อัปเดต AddClassModal state + onAdd logic**

```typescript
// state ใน AddClassModal:
const [name, setName] = useState('');
const [selectedTypes, setSelectedTypes] = useState<string[]>([]);

// onAdd ส่ง selectedTypes ออกมาด้วย
const handleAdd = () => {
  if (!name.trim() && selectedTypes.length === 0) return;
  const finalName = name.trim() || selectedTypes[0];
  onAdd(finalName, selectedTypes);
};
```

- [ ] **Step 5: อัปเดต addClass ใน ClassesClient ให้รับ selectedTypes**

```typescript
const addClass = (name: string, selectedTypes: string[] = []) => {
  if (!name.trim()) return;
  // รวม keywords จากทุก type ที่เลือก
  const allDefaults = Array.from(new Set(
    selectedTypes.flatMap(t => (DEFAULT_KEYWORDS_BY_CLASS as Record<string, string[]>)[t] || [])
  ));
  const defaults = allDefaults.length > 0
    ? allDefaults
    : (DEFAULT_KEYWORDS_BY_CLASS as Record<string, string[]>)[name.trim()] || [];
  const newClass: BusinessClass = {
    id: `c${Date.now()}`,
    name: name.trim(),
    color: CLASS_COLORS[classes.length % CLASS_COLORS.length],
    geo: { mode: 'province', provinces: [], districts: [], tambons: [], gps: null, radiusKm: 0 },
    keywords: [...defaults],
    defaultKeywords: defaults,
  };
  setClasses(prev => [...prev, newClass]);
  setShowAdd(false);
  setEditingId(newClass.id);
  saveToServer([...classes, newClass]);
};
```

- [ ] **Step 6: เปลี่ยน tab label "Keywords" → "ประเภทธุรกิจ" ใน EditClassDrawer**

```tsx
{t === 'keywords' ? 'ประเภทธุรกิจ' : ...}
```

- [ ] **Step 7: อัปเดต KeywordEditor ให้มี checkbox section ก่อน custom keywords**

ใน `KeywordEditor` เพิ่มด้านบน ก่อน input field:
```tsx
<div>
  <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 8 }}>ประเภทธุรกิจที่รับ</div>
  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
    {CLASS_SUGGESTIONS.map(s => {
      const defaultsForType = (DEFAULT_KEYWORDS_BY_CLASS as Record<string, string[]>)[s] || [];
      const isSelected = defaultsForType.some(k => cls.keywords.includes(k));
      return (
        <button key={s}
          className={isSelected ? 'p-chip p-chip-gold' : 'p-chip p-chip-outline'}
          style={{ cursor: 'pointer' }}
          onClick={() => {
            if (isSelected) {
              onChange({ keywords: cls.keywords.filter(k => !defaultsForType.includes(k)) });
            } else {
              onChange({ keywords: Array.from(new Set([...cls.keywords, ...defaultsForType])) });
            }
          }}>
          {isSelected && <Icons.Check size={10} />}{s}
        </button>
      );
    })}
  </div>
</div>
```

- [ ] **Step 8: Fix บันทึก navigation — ปิด drawer หลัง save**

ใน `KeywordEditor` แก้ onSave button:
```tsx
// ปัจจุบัน: onClick={() => { setSaved(true); setTimeout(() => setSaved(false), 2200); onSave(); }}
// แก้เป็น:
onClick={() => {
  onSave(); // onSave = onClose ใน EditClassDrawer → ปิด drawer ทันที
}}
```

ใน `EditClassDrawer`:
```tsx
{tab === 'keywords' && <KeywordEditor cls={cls} onChange={onChange} onSave={onClose} />}
```
(เหมือนเดิม แต่ตรวจว่า KeywordEditor ส่ง onSave ไปที่ onClose จริง ไม่ใช่ no-op)

- [ ] **Step 9: Commit**

```bash
git add src/app/portal/classes/_client.tsx src/lib/portal-data.ts
git commit -m "feat(classes): rename Business Class → บริษัท, keywords เป็น checkboxes, fix save navigation"
```

---

## Task 5: OpenStreetMap mini-map ด้วย Leaflet

**Files:**
- Create: `src/app/portal/classes/_map-preview.tsx`
- Modify: `src/app/portal/classes/_client.tsx` — แทนที่ fake map grid
- Modify: `package.json` / install leaflet

- [ ] **Step 1: ติดตั้ง leaflet**

```bash
cd dashboard/web && npm install leaflet @types/leaflet
```

- [ ] **Step 2: สร้าง _map-preview.tsx**

```typescript
'use client';
// Dynamic import ป้องกัน SSR error (Leaflet ใช้ window)

import { useEffect, useRef } from 'react';

interface MapPreviewProps {
  lat: number;
  lng: number;
  radiusKm: number;
}

export function MapPreview({ lat, lng, radiusKm }: MapPreviewProps) {
  const divRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<import('leaflet').Map | null>(null);
  const circleRef = useRef<import('leaflet').Circle | null>(null);

  useEffect(() => {
    if (!divRef.current) return;
    if (typeof window === 'undefined') return;

    import('leaflet').then(L => {
      // Fix default icon paths for Next.js
      delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
        iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
      });

      if (!mapRef.current && divRef.current) {
        mapRef.current = L.map(divRef.current, { zoomControl: true, scrollWheelZoom: false })
          .setView([lat, lng], 10);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '© OpenStreetMap',
          maxZoom: 18,
        }).addTo(mapRef.current);
        L.marker([lat, lng]).addTo(mapRef.current);
      } else if (mapRef.current) {
        mapRef.current.setView([lat, lng], 10);
      }

      if (circleRef.current) circleRef.current.remove();
      if (radiusKm > 0 && mapRef.current) {
        circleRef.current = L.circle([lat, lng], {
          radius: radiusKm * 1000,
          color: '#C8A86A',
          fillColor: 'rgba(200, 168, 106, 0.12)',
          fillOpacity: 1,
          weight: 1.5,
        }).addTo(mapRef.current);
        mapRef.current.fitBounds(circleRef.current.getBounds(), { padding: [20, 20] });
      }
    });

    return () => {
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
    };
  }, [lat, lng, radiusKm]);

  return (
    <>
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
      <div ref={divRef} style={{ height: 200, borderRadius: 10, overflow: 'hidden', border: '1px solid var(--line)' }} />
    </>
  );
}
```

- [ ] **Step 3: แทนที่ fake map ใน _client.tsx**

ใน `GeoEditor` หา block `{/* Mini map preview */}` แล้วแทนที่ทั้ง `<div>` นั้น:

```tsx
import dynamic from 'next/dynamic';
const MapPreview = dynamic(() => import('./_map-preview').then(m => m.MapPreview), { ssr: false });

// ใน GeoEditor ส่วน Mode 2:
{cls.geo.gps && (
  <MapPreview
    lat={cls.geo.gps.lat}
    lng={cls.geo.gps.lng}
    radiusKm={cls.geo.radiusKm}
  />
)}
{!cls.geo.gps && (
  <div className="p-mono p-fg-dim" style={{ textAlign: 'center', padding: 20, background: 'var(--surface-2)', borderRadius: 10, fontSize: 11 }}>
    วาง Google Maps link เพื่อดูแผนที่
  </div>
)}
```

- [ ] **Step 4: ทดสอบ — เปิด browser วาง Google Maps link ดูว่า map แสดง**

```bash
cd dashboard/web && npm run dev
# เปิด http://localhost:3000/portal/classes
# เพิ่มบริษัท → แก้ไข → พื้นที่ครอบคลุม → Mode 2
# วาง coords เช่น 48.1234, 104.5678
# ตรวจว่า Leaflet map โหลด + วงกลมแสดง
```

- [ ] **Step 5: Commit**

```bash
git add src/app/portal/classes/_map-preview.tsx src/app/portal/classes/_client.tsx dashboard/web/package.json dashboard/web/package-lock.json
git commit -m "feat(map): แทน fake grid ด้วย Leaflet OpenStreetMap จริง"
```

---

## Task 6: Per-company Filter Settings (budget/SME/MIT/notifyTime)

**Files:**
- Modify: `src/lib/portal-data.ts` — เพิ่ม filter fields ใน BusinessClass
- Modify: `src/app/portal/classes/_client.tsx` — เพิ่ม tab "ตัวกรอง"

### 6a: อัปเดต types

- [ ] **Step 1: เพิ่ม filter fields ใน BusinessClass interface**

```typescript
export interface BusinessClass {
  id: string;
  name: string;
  color: string;
  geo: BusinessClassGeo;
  keywords: string[];
  defaultKeywords: string[];
  // ใหม่:
  budgetMinBaht?: number;   // หน่วย บาท (ไม่ใช่ ล้านบาท)
  budgetMaxBaht?: number;
  isSME?: boolean;
  isMIT?: boolean;
  notifyTime?: string;      // "06:00"
}
```

### 6b: เพิ่ม tab "ตัวกรอง" ใน EditClassDrawer

- [ ] **Step 2: อัปเดต tab array ใน EditClassDrawer**

```tsx
// เดิม: ['geo', 'keywords', 'name'] as const
// ใหม่:
const [tab, setTab] = useState<'geo' | 'keywords' | 'filter' | 'name'>('geo');

// ใน tabs render:
{(['geo', 'keywords', 'filter', 'name'] as const).map(t => (
  <button key={t} className={`p-tab${tab === t ? ' active' : ''}`} onClick={() => setTab(t)}>
    {t === 'geo' ? 'พื้นที่' : t === 'keywords' ? 'ประเภทธุรกิจ' : t === 'filter' ? 'ตัวกรอง' : 'ชื่อ'}
  </button>
))}
```

- [ ] **Step 3: สร้าง FilterEditor component**

```tsx
function FilterEditor({ cls, onChange, onSave }: { cls: BusinessClass; onChange: (patch: Partial<BusinessClass>) => void; onSave: () => void }) {
  const [saved, setSaved] = useState(false);
  const budgetMin = cls.budgetMinBaht ?? 100000;
  const budgetMax = cls.budgetMaxBaht ?? 50000000;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <ButlerNote>
        Sebastian จะแจ้งเตือนงานที่ตรงกับตัวกรองนี้ — แยกตั้งค่าได้รายบริษัท
      </ButlerNote>

      <Field label="งบขั้นต่ำ (บาท)">
        <input className="p-input" type="number" step="100000" min="0"
          value={budgetMin}
          onChange={e => onChange({ budgetMinBaht: parseInt(e.target.value) || 0 })}
          placeholder="100000" />
        <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 4 }}>= {(budgetMin / 1000000).toFixed(2)} ล้านบาท</div>
      </Field>

      <Field label="งบสูงสุด (บาท)">
        <input className="p-input" type="number" step="1000000" min="0"
          value={budgetMax}
          onChange={e => onChange({ budgetMaxBaht: parseInt(e.target.value) || 0 })}
          placeholder="50000000" />
        <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 4 }}>= {(budgetMax / 1000000).toFixed(2)} ล้านบาท</div>
      </Field>

      <div className="p-card" style={{ padding: '0 16px' }}>
        <div style={{ borderBottom: '1px solid var(--line)' }}>
          <Toggle value={cls.isSME ?? false} onChange={v => onChange({ isSME: v })}
            label="บริษัทเป็น SME" hint="แสดงงานที่กำหนด SME ได้" />
        </div>
        <Toggle value={cls.isMIT ?? false} onChange={v => onChange({ isMIT: v })}
          label="สินค้า Made in Thailand" hint="แสดงงานที่กำหนด MIT" />
      </div>

      <Field label="เวลาแจ้งเตือน" hint="Sebastian จะส่ง LINE ตามเวลานี้">
        <input className="p-input" type="time"
          value={cls.notifyTime ?? '06:00'}
          onChange={e => onChange({ notifyTime: e.target.value })} />
      </Field>

      <button className="p-btn p-btn-primary" onClick={() => { setSaved(true); setTimeout(() => setSaved(false), 2000); onSave(); }}
        style={{ width: '100%', height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
        {saved ? <><Icons.Check2 size={16} />บันทึกเสร็จแล้ว</> : <><Icons.Check size={16} />บันทึกตัวกรอง</>}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: เพิ่ม FilterEditor ใน EditClassDrawer content area**

```tsx
{tab === 'filter' && <FilterEditor cls={cls} onChange={onChange} onSave={onClose} />}
```

- [ ] **Step 5: Commit**

```bash
git add src/lib/portal-data.ts src/app/portal/classes/_client.tsx
git commit -m "feat(classes): เพิ่ม tab ตัวกรอง (budget/SME/MIT/notifyTime) per company"
```

---

## Task 7: Profile Redesign — เพิ่ม LINE ID + Account Status

**Files:**
- Modify: `src/app/portal/profile/_client.tsx`
- Modify: `src/app/portal/profile/page.tsx` — ส่ง lineUserId + expiry ลงมา (ตรวจสอบว่ามีแล้ว)

- [ ] **Step 1: อ่าน profile/page.tsx ตรวจสอบ props**

```bash
cat dashboard/web/src/app/portal/profile/page.tsx
```

- [ ] **Step 2: เพิ่ม lineUserId ใน props interface**

ใน `ProfileClient` interface:
```typescript
interface Props {
  lineUserId: string;
  displayName: string;     // ชื่อ LINE
  initialProfile: PortalProfile;
  classCount: number;
  registeredAt: string;
  tierId: string;
  expiryLabel: string;     // ใหม่ — วันหมดอายุ
  daysLeft: number;        // ใหม่
}
```

- [ ] **Step 3: เพิ่มส่วน Account Status ก่อน Save button**

```tsx
<DividerOrnate label="สถานะบัญชี" />

<div className="p-card" style={{ marginBottom: 14, padding: 16 }}>
  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
    <div>
      <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em' }}>แพ็กเกจ</div>
      <div className="p-display" style={{ fontSize: 18, marginTop: 2 }}>{tierId}</div>
    </div>
    <div>
      <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em' }}>วันหมดอายุ</div>
      <div className="p-display" style={{ fontSize: 15, marginTop: 2, color: daysLeft <= 7 ? 'var(--wine-soft)' : 'var(--accent)' }}>
        {expiryLabel}
      </div>
      <div className="p-fg-dim" style={{ fontSize: 11 }}>เหลือ {daysLeft} วัน</div>
    </div>
    <div>
      <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em' }}>LINE ID</div>
      <div className="p-mono" style={{ fontSize: 12, marginTop: 2, wordBreak: 'break-all' }}>{lineUserId}</div>
    </div>
    <div>
      <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em' }}>สมัครเมื่อ</div>
      <div style={{ fontSize: 13, marginTop: 2 }}>{registeredAt}</div>
    </div>
  </div>
</div>
```

- [ ] **Step 4: ลบ Quick stats section เก่า** (ที่อยู่หลัง Save button ซ้ำซ้อนกัน)

ลบ block:
```tsx
{/* Quick stats */}
<div className="p-card" style={{ marginBottom: 16, padding: 14 }}>
  ...
</div>
```

- [ ] **Step 5: ตรวจสอบว่า profile/page.tsx ส่ง expiryLabel + daysLeft มาแล้ว**

ดู world/page.tsx เป็น reference (มี daysLeft + expiryLabel อยู่แล้ว) ใน profile/page.tsx เพิ่ม:
```typescript
let daysLeft = 30;
let expiryLabel = '';
if (customer?.expires_at) {
  const expiry = new Date(customer.expires_at);
  daysLeft = Math.max(0, Math.ceil((expiry.getTime() - Date.now()) / 86400000));
  expiryLabel = expiry.toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric' });
}
```

และส่ง `expiryLabel`, `daysLeft` เข้า `ProfileClient`.

- [ ] **Step 6: Commit**

```bash
git add src/app/portal/profile/_client.tsx src/app/portal/profile/page.tsx
git commit -m "feat(profile): เพิ่ม LINE ID, account status, expiry display"
```

---

## Task 8: World — Star/Favorite System + งานที่สนใจ

**Files:**
- Modify: `src/lib/portal-data.ts` — เพิ่ม starred ใน PortalNotes
- Modify: `src/app/portal/world/_client.tsx` — star button + section

### 8a: เพิ่ม starred ใน PortalNotes

- [ ] **Step 1: อัปเดต PortalNotes type**

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
  starred?: string[];    // ใหม่ — array ของ job IDs
}
```

### 8b: อัปเดต WorldClient

- [ ] **Step 2: เพิ่ม starred state + save function**

```typescript
// Props เพิ่ม:
// initialStarred: string[]

const [starred, setStarred] = useState<Set<string>>(new Set(props.initialStarred ?? []));
const [savingStars, setSavingStars] = useState(false);

const toggleStar = async (jobId: string) => {
  const next = new Set(starred);
  if (next.has(jobId)) next.delete(jobId);
  else next.add(jobId);
  setStarred(next);
  setSavingStars(true);
  try {
    await fetch('/api/portal/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ starred: Array.from(next) }),
    });
  } finally { setSavingStars(false); }
};
```

- [ ] **Step 3: เพิ่ม star button ใน JobCard**

```tsx
function JobCard({ job, cls, starred, onStar }: { job: PortalJob; cls?: BusinessClass; starred: boolean; onStar: () => void }) {
  // ... ใน top-right ของ card:
  <button onClick={e => { e.stopPropagation(); onStar(); }}
    style={{ background: 'none', border: 'none', cursor: 'pointer', color: starred ? 'var(--accent)' : 'var(--fg-dim)', fontSize: 18, padding: '0 4px' }}>
    {starred ? '★' : '☆'}
  </button>
}
```

- [ ] **Step 4: เพิ่ม "งานที่สนใจ" section ก่อนรายการงาน**

```tsx
{starred.size > 0 && (
  <div style={{ marginBottom: 20 }}>
    <div className="p-label" style={{ marginBottom: 8 }}>⭐ งานที่สนใจ ({starred.size})</div>
    {jobs.filter(j => starred.has(j.id)).map(job => (
      <JobCard key={job.id} job={job} cls={classes.find(c => c.id === job.matchedClassId)}
        starred={true} onStar={() => toggleStar(job.id)} />
    ))}
  </div>
)}
```

- [ ] **Step 5: อัปเดต world/page.tsx ให้ส่ง starred มาด้วย**

```typescript
const starred = notes.starred ?? [];
// ใน return:
<WorldClient ... initialStarred={starred} />
```

- [ ] **Step 6: Commit**

```bash
git add src/lib/portal-data.ts src/app/portal/world/_client.tsx src/app/portal/world/page.tsx
git commit -m "feat(world): star/favorite jobs + งานที่สนใจ section"
```

---

## Task 9: File Upload Per Company

**Files:**
- Create: `src/app/api/portal/upload/route.ts`
- Modify: `src/lib/portal-data.ts` — เพิ่ม files ใน BusinessClass
- Modify: `src/app/portal/classes/_client.tsx` — เพิ่ม tab "เอกสาร"

> **Note:** เก็บไฟล์ใน Vercel Blob (ต้องมี BLOB_READ_WRITE_TOKEN) หรือถ้ายังไม่มีให้ใช้ base64 in PortalNotes (จำกัดขนาด). แผนนี้ใช้ Vercel Blob.

### 9a: ติดตั้งและตั้งค่า

- [ ] **Step 1: ติดตั้ง @vercel/blob**

```bash
cd dashboard/web && npm install @vercel/blob
```

- [ ] **Step 2: เพิ่ม files ใน BusinessClass type**

```typescript
export interface CompanyFile {
  name: string;
  url: string;
  uploadedAt: string;
  sizeBytes: number;
}

export interface BusinessClass {
  // ... existing fields ...
  files?: CompanyFile[];
}
```

### 9b: สร้าง upload API route

- [ ] **Step 3: สร้าง `src/app/api/portal/upload/route.ts`**

```typescript
import { NextRequest, NextResponse } from 'next/server';
import { put } from '@vercel/blob';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';

export async function POST(req: NextRequest) {
  const sessionValue = req.cookies.get(COOKIE_NAME)?.value;
  if (!sessionValue) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const session = await parseSessionCookie(sessionValue);
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const formData = await req.formData();
  const file = formData.get('file') as File | null;
  const companyId = formData.get('companyId') as string;

  if (!file || !companyId) return NextResponse.json({ error: 'Missing file or companyId' }, { status: 400 });
  if (file.size > 10 * 1024 * 1024) return NextResponse.json({ error: 'ไฟล์ใหญ่เกิน 10MB' }, { status: 413 });

  const blob = await put(
    `portal/${session.lineUserId}/${companyId}/${file.name}`,
    file,
    { access: 'public', addRandomSuffix: true },
  );

  return NextResponse.json({ url: blob.url, name: file.name, sizeBytes: file.size });
}
```

### 9c: เพิ่ม tab "เอกสาร" ใน EditClassDrawer

- [ ] **Step 4: อัปเดต tab array ใน EditClassDrawer เป็น 5 tabs**

```typescript
const [tab, setTab] = useState<'geo' | 'keywords' | 'filter' | 'docs' | 'name'>('geo');
```

Tab labels: พื้นที่ / ประเภท / ตัวกรอง / เอกสาร / ชื่อ

- [ ] **Step 5: สร้าง DocsEditor component**

```tsx
function DocsEditor({ cls, onChange }: { cls: BusinessClass; onChange: (patch: Partial<BusinessClass>) => void }) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const files = cls.files ?? [];

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('companyId', cls.id);
      const res = await fetch('/api/portal/upload', { method: 'POST', body: fd });
      if (!res.ok) { setError('อัปโหลดล้มเหลว'); return; }
      const data = await res.json();
      const newFile: CompanyFile = { name: data.name, url: data.url, uploadedAt: new Date().toISOString(), sizeBytes: data.sizeBytes };
      onChange({ files: [...files, newFile] });
    } catch { setError('เกิดข้อผิดพลาด'); }
    finally { setUploading(false); e.target.value = ''; }
  };

  const removeFile = (url: string) => onChange({ files: files.filter(f => f.url !== url) });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <ButlerNote>
        อัปโหลดเอกสารที่เกี่ยวข้องกับบริษัทนี้ — Sebastian จะช่วยอ่านและสรุปข้อมูลสำคัญ
      </ButlerNote>
      <label className="p-btn p-btn-ghost" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, cursor: 'pointer' }}>
        <Icons.Plus size={16} />
        {uploading ? 'กำลังอัปโหลด…' : 'เลือกไฟล์'}
        <input type="file" accept=".pdf,.doc,.docx,.xlsx,.jpg,.png" onChange={handleUpload} style={{ display: 'none' }} disabled={uploading} />
      </label>
      {error && <div style={{ color: 'var(--wine-soft)', fontSize: 13 }}>{error}</div>}
      {files.length === 0 && <div className="p-fg-dim" style={{ fontSize: 13, fontStyle: 'italic', textAlign: 'center' }}>ยังไม่มีเอกสาร</div>}
      {files.map(f => (
        <div key={f.url} className="p-card" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Icons.Doc size={16} style={{ color: 'var(--accent)', flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</div>
            <div className="p-fg-dim" style={{ fontSize: 11 }}>{(f.sizeBytes / 1024).toFixed(0)} KB · {f.uploadedAt.slice(0, 10)}</div>
          </div>
          <a href={f.url} target="_blank" rel="noreferrer" className="p-icon-btn"><Icons.ChevronRight size={14} /></a>
          <button className="p-icon-btn" onClick={() => removeFile(f.url)} style={{ color: 'var(--wine-soft)' }}><Icons.Trash size={14} /></button>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: เพิ่ม DocsEditor ใน EditClassDrawer content**

```tsx
{tab === 'docs' && <DocsEditor cls={cls} onChange={onChange} />}
```

- [ ] **Step 7: เพิ่ม import CompanyFile ในส่วนที่ต้องการ**

ใน `classes/_client.tsx` เพิ่ม:
```typescript
import type { BusinessClass, CompanyFile } from '@/lib/portal-data';
```

- [ ] **Step 8: Commit**

```bash
git add src/app/api/portal/upload/route.ts src/lib/portal-data.ts src/app/portal/classes/_client.tsx dashboard/web/package.json
git commit -m "feat(docs): file upload per company — Vercel Blob + เอกสาร tab"
```

---

## Self-Review Checklist

### Spec Coverage

| Item | Task | Status |
|---|---|---|
| 1. discount % ต่อ bidder + avg/stddev company | Task 1 + Task 2 | ✅ |
| 2. Bottom tab bar (LINE-style) | Task 3 (global nav) + Task 2 (3-tab) | ✅ |
| 3. Business Class → บริษัท; keywords → checkboxes | Task 4 | ✅ |
| 4. Slider fix + distance + OpenStreetMap | Task 5 | ✅ |
| 5. Keyword defaults + บันทึก navigation fix | Task 4 | ✅ |
| 6. Budget (บาท) + SME/MIT + notifyTime per company | Task 6 | ✅ |
| 7. Profile: LINE ID + account status | Task 7 | ✅ |
| 8. World: star/favorite + งานที่สนใจ | Task 8 | ✅ |
| 9. Own company bid history tab | Task 2 (tab 3 + API) | ✅ |
| 10. File upload per company | Task 9 | ✅ |

### Type Consistency
- `BusinessClass` ใน `portal-data.ts` เพิ่ม `budgetMinBaht?, budgetMaxBaht?, isSME?, isMIT?, notifyTime?, files?`
- `PortalNotes` เพิ่ม `starred?: string[]`
- `CompetitorProfile` ใน `bid-history.ts` เพิ่ม `avg_discount_from_budget_pct, stddev_discount_pct`
- `CompanyFile` สร้างใหม่ใน `portal-data.ts`

### Potential Issues
- **Leaflet SSR**: ต้อง `dynamic(() => import('./_map-preview'), { ssr: false })` — covered in Task 5 Step 3
- **Vercel Blob**: ต้องตั้ง `BLOB_READ_WRITE_TOKEN` ใน Vercel env vars ถ้ายังไม่มี
- **DB materialized view**: `REFRESH MATERIALIZED VIEW CONCURRENTLY` ต้องมี unique index (มีแล้วใน schema)
- **5-tab nav**: font-size 9px อาจเล็กเกินบางเครื่อง — ให้ทดสอบบน mobile จริง

---

## Execution Order

Tasks ควรทำตามลำดับนี้ (dependencies):

```
Task 1 (DB) → Task 2 (History UI) → Task 3 (Nav) → Task 4 (Rename+Keywords)
→ Task 5 (Map) → Task 6 (Filter tab) → Task 7 (Profile) → Task 8 (Stars) → Task 9 (Files)
```

Tasks 3-9 ทำ parallel ได้ (ไม่ depend กัน)
