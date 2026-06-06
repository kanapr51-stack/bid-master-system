# Tambon-Level Competitor Intel — Design Spec

**วันที่:** 2026-06-07 · **สถานะ:** APPROVED (brainstorm กับกัญจน์) · ต่อยอดจาก [`cgd_intel`](2026-06-06-cgd-competitive-intel-design.md)

## เป้าหมาย
ยกระดับ competitive intel ในการ์ด D0 จาก **ภาพรวมระดับจังหวัด** → **โปรไฟล์คู่แข่งรายบริษัทระดับท้องถิ่น** (ตำบล/อำเภอ) เพื่อตอบคำถามจริงของผู้รับเหมา: *"งานนี้เราสู้กับใคร และเขาลดราคากันยังไง"*

**Pain ที่แก้ (กัญจน์):** สถิติระดับจังหวัดเจือจางด้วยบริษัทที่ไม่ใช่คู่แข่งของพื้นที่งานนั้น คู่แข่งจริงระบุได้ดีกว่าจาก *track record งานแข่งราคาในพื้นที่* ไม่ใช่ค่าเฉลี่ยทั้งจังหวัด

## หลักการ (2 แกนแยกกัน — กุญแจของดีไซน์)
1. **Selection (ใครคือคู่แข่งแถบนี้)** — ใช้ location เจาะ: บริษัทที่เคยชนะงาน *work-type นี้* ใน **ตำบล → อำเภอ → จังหวัด** (ไล่ระดับจนได้คู่แข่งพอ)
2. **Per-company stat (ลดเท่าไหร่)** — คิดจาก **ประวัติของบริษัทนั้นทั้งหมด** (work-type เดียวกัน, target provinces, 3 ปีล่าสุด, competitive-set) → n ต่อบริษัทมากพอ ตัวเลขนิ่ง ไม่แกว่งแม้พื้นที่งานบาง

> เหตุผลแกน 2: ที่ระดับอำเภอแต่ละบริษัททำแค่ 1–2 งาน (verify: บ้านแพงถนน 3 ปี ทุกเจ้า ≤2 งาน) → ถ้าคิด IQR จากแค่พื้นที่ก็ไม่มีความหมาย ต้องคิดจากประวัติบริษัทที่กว้างกว่า

## ⚠️ Invariant สำคัญ (กัญจน์เน้น 2026-06-07)
**`COMPETITIVE_SET` filter ใช้ทั้ง selection และ per-company stat** — คู่แข่งคือบริษัทที่เล่นในสนามประมูล (e-bidding/สอบราคา/คัดเลือก/ประกวดราคาฯ) เท่านั้น **บริษัทที่ได้แต่งานเฉพาะเจาะจง (จ้างตรง) ไม่ใช่คู่แข่ง → ไม่เอามาคิดทั้ง 2 จุด** (งานเฉพาะเจาะจง disc≈0 ลาก median ลงด้วย ยิ่งต้องตัด)

## Non-Goals
- ❌ แนะนำราคาที่ควรยื่น (ยังคง descriptive ไม่ prescriptive)
- ❌ resolve ตำบลแบบ realtime ทุกงานด้วย API หนักๆ (ใช้ฟรีก่อน, API เป็น fallback สุดท้าย)
- ❌ คู่แข่งจากงานจ้างตรง

## Architecture
ต่อยอดโมดูล `scripts/cgd_intel.py` (ไม่สร้างโมดูลใหม่ — domain เดียวกัน) + reuse location resolver จาก `job_matcher`.

```
intel_lines(province, project_name, project_id, dept_name)   # เพิ่ม args
 ├─ resolve_location() → (tambon, amphoe)  [tambon_from_name→_dept→_api + tambon_lookup]
 ├─ select_competitors(work_type, tambon, amphoe, province)  # ไล่ระดับ + competitive-set
 ├─ company_stats(winner, work_type)                          # median+IQR ประวัติบริษัท
 ├─ area_stats(rows ที่ resolved level)                        # ภาพรวมเสริม
 └─ confidence_label(n, iqr_width)
```

## Components

### `resolve_location(project_id, project_name, dept_name) -> (tambon, amphoe)`
- ลำดับ (ฟรีก่อน): `job_matcher.tambon_from_name` → `tambon_from_dept` → `tambon_from_api` (rate-limited, fallback สุดท้าย)
- map ตำบล→อำเภอ ผ่าน `data/tambon_lookup.json`
- **ตำบลซ้ำข้ามอำเภอ** (เช่น ต.โพนทอง อยู่ทั้งบ้านแพง+เรณูนคร): ถ้า lookup คืนหลายอำเภอ และระบุอำเภอไม่ได้จาก context (dept_name) → คืน amphoe=None (จะ fallback ข้ามไประดับจังหวัด)
- คืน `('', '')` ได้ (resolve ไม่ได้) → ระบบ degrade เป็นจังหวัด

### `select_competitors(work_type_tokens, tambon, amphoe, province, conn) -> (rows, level)`
ไล่ระดับ คืน rows + level ที่ใช้:
1. **tambon**: `WHERE subdistrict=? AND district=?` (คู่กัน กันตำบลซ้ำ) + competitive + recent FY + win_price>0 + work-type LIKE
2. ถ้า distinct winners < `MIN_COMPETITORS` → **amphoe**: `WHERE district=?`
3. ถ้ายังไม่พอ → **province**: `WHERE province=?`
4. คืน level สุดท้ายที่ใช้ (`tambon`/`amphoe`/`province`) ไปทำ header
- ถ้า province ยังได้ 0 บริษัท → คืน `([], None)` → omit

### `company_stats(winner, work_type_tokens, conn) -> dict`
- query งานของ **winner รายนั้น**: competitive + recent FY + win_price>0 + work-type LIKE + target provinces (ไม่จำกัด location ย่อย — เอาประวัติให้กว้าง)
- คืน `{games, discount_median, discount_p25, discount_p75}` (reuse `_pct`)
- `games < 3` → p25/p75 = None (โชว์แค่ median; 1 งาน = ค่าเดียว)

### `confidence_label(area_n, iqr_width) -> str`
- 🟢 เชื่อถือได้: `area_n >= 30`
- 🟡 ปานกลาง: `10 <= area_n < 30` **หรือ** IQR กว้าง (p75−p25 > 20)
- 🔴 ข้อมูลน้อย: `area_n < 10`
- ป้ายสื่อ **ความนิ่งทางสถิติ** (จาก n+IQR) — คนละมิติกับ relevance (ซึ่งสื่อผ่าน header ว่าใช้ level ไหน)

### `intel_lines(...)` orchestrate + format
- top `SHOW_N = 3` บริษัท เรียงตามจำนวนงานใน selection (active สุด = น่ายื่นอีก)
- header ระบุ level: `(งาน{work-type} ต.{tambon} อ.{amphoe})` / `(... อ.{amphoe})` / `(...ใน{province})`
- ต่อบริษัท: `≥3 งาน → "{ชื่อ} · {n} งาน · ลด {med}% ({p25}–{p75}%)"` · `1–2 งาน → "{ชื่อ} · {n} งาน · ลด {med}%"`
- ภาพรวมเสริม: `📊 ภาพรวม {area_n} งาน · ลด {p25}–{p75}%` (โชว์เมื่อ p75>0; ตาม principle เดิม)
- ป้ายความเชื่อมั่นปิดท้าย

> **หมายเหตุ (จงใจ ไม่ใช่บั๊ก):** "{n} งาน" ข้างบริษัท = ประวัติบริษัทนั้น (broad, work-type+provinces) ส่วน "ภาพรวม {area_n} งาน" = งานใน scope พื้นที่ที่ resolve ได้ (local) → ค่าต่างกันเป็นปกติ (บริษัทอาจมีประวัติ 11 งาน ขณะที่พื้นที่มี 9 งาน). label คนละคำ ('X งาน' ต่อบริษัท vs 'ภาพรวม X งาน') กันสับสน — **ห้าม implementer 'แก้' ให้เท่ากัน**

### Output ตัวอย่าง (กัญจน์ approve)
```
💡 ราคาอ้างอิง (งานถนน ต.โพนทอง อ.บ้านแพง)
🏆 คู่แข่งแถบนี้:
  • หจก.เอส.ที.เค.เพาเวอร์ · 8 งาน · ลด 12% (8–15%)
  • หจก.ยศประทานรุ่งเรืองทรัพย์ · 11 งาน · ลด 9% (6–13%)
📊 ภาพรวม 9 งาน · ลด 11–28%
🟡 เชื่อมั่นปานกลาง — ข้อมูลน้อย+ช่วงกว้าง (ดูเป็นแนวโน้ม ไม่ใช่ราคาตายตัว)
```

## Schema / Sync
- **migrate v121**: `cgd_winners ADD COLUMN district TEXT` + `ADD COLUMN subdistrict TEXT` (additive)
- `cgd_sync_to_vps`: `extract_subset` SELECT + `_MERGE_SQL` + buf tuple เพิ่ม 2 field
- **re-sync 617K** (winner_history มี district 100%, subdistrict 91%)

## Wiring — `Sebastian_LINE_Sender.format_notification`
ส่ง `project_id` + `dept_name` เข้า `intel_lines` เพิ่ม (มีอยู่ใน format_notification แล้ว) เพื่อให้ resolver ใช้. try/except ครอบเหมือนเดิม — intel พังห้ามทำ D0 พัง.

## Config (ค่าเริ่ม — ปรับได้)
`MIN_COMPETITORS = 2` (distinct winners ขั้นต่ำก่อนหยุด fallback) · `SHOW_N = 3` · `MIN_GAMES_FOR_IQR = 3` · confidence: 30/10, IQR_WIDE = 20

## Edge / Safety
- resolve ตำบลไม่ได้ → degrade province (per-company profile ยังทำงาน ดีกว่า intel เดิม)
- ตำบล ambiguous → ข้ามไป province
- ไม่มีคู่แข่ง competitive เลย → omit เงียบ
- ทุก error swallow ที่ wiring · `tambon_from_api` ใช้เป็น fallback สุดท้าย (D0 volume ต่ำ)

## Testing (TDD) — `test_cgd_intel.py` (เพิ่ม)
1. `resolve_location`: name/dept resolve, ตำบลซ้ำอำเภอ → amphoe=None, resolve ไม่ได้ → ('','')
2. `select_competitors`: ไล่ระดับ tambon→amphoe→province (fixture ตำบลน้อย→ขยาย), competitive-set กรอง (เฉพาะเจาะจงไม่หลุด), tambon ใช้คู่ subdistrict+district
3. `company_stats`: median/IQR จากประวัติบริษัท, games<3 → ไม่มี IQR, competitive-only
4. `confidence_label`: thresholds 30/10 + IQR กว้าง
5. `intel_lines`: format (ป้ายสี+เลขย่อ), header ตาม level, degrade province-only, omit เมื่อไม่มีคู่แข่ง
6. graceful: cgd_winners ไม่มี table/column → []

## Rollback
revert wiring args + ฟังก์ชันใหม่ใน cgd_intel (intel เดิม province-level ยังอยู่ได้). v121/re-sync เป็น additive — ไม่ต้อง rollback DB
