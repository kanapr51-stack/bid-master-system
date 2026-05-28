# Thai Service Dashboard Design

_Started 2026-05-19 16:29 UTC_

---

## User

<system-info comment="Only acknowledge these if relevant">
Project title is now "Bid Master System 2"
Current date is now May 19, 2026
</system-info>

<default aesthetic>
If no references, art direction or design systems were provided, use this default professional modern, minimal aesthetic as a base. Declare your choice out loud so you stick to it. Guidance:
- Choose a type pairing from web-safe set or Google Fonts. Helvetica is a good choice. Avoid hard-to-read or overly stylized fonts. Use 1-3 fonts only.
- Foreground and background: choose a color tone (warm, cool, neutral, something in-between). Use subtly-toned whites and blacks; avoid saturations above 0.02 for whites.
- Accents: choose 0-2 additional accent colors using oklch. All accents should share same chroma and lightness; vary hue.
- NEVER write out an SVG yourself that's more complicated than a square, circle, diamond, etc.
- For imagery, never hand-draw SVGs; use subtly-striped SVG placeholders instead with monospace explainers for what should be dropped there (e.g. “product shot”)

CRITICAL: ignore default aesthetic entirely if given other aesthetic instructions like reference images, design systems or guidance, or if there are files in the project already.
</default aesthetic>

<pasted_text name="Pasted text (56 lines)">
นายช่วยออกแบบเว็ปไซส์ที่เป็น master system ของบริษัทรับเหมาก่อสร้างให้ที  โดยที่จะใช้เว็บไซต์นี้ในการกรอกข้อมูลเพื่อให้ Sebastian ที่เป็น Chatbot ใน Line รู้ข้อมูลของบริษัท ของลูกค้า เพื่อทำการแจ้งเตือนงานใหม่จากเว็บไซต์ประมูลงานภาครัฐ แต่ว่าระบบ Sebastian ไม่ได้มีแค่นั้น Sebastian ยังสามารถวิเคราะห์งานคู่แข่ง จัดเอกสาร อ่านเอกสารให้ได้ด้วยเหมือนกับพ่อบ้านหรือเลขาส่วนตัว
เว็ปไซส์ชื่อ: Sebastian
  Theme: Sebastian จาก Black Butler
เน้นไปที่การทำให้ปุ่มต่างๆรู้ว่ากดทำไมและใช้งานง่าย
     
  === PAGES & FEATURES === 

  PAGE 1 — Login
  - ปุ่ม Login with LINE
  - แสดง package tiers ให้เห็นก่อน login

  PAGE 2 — Company World (หน้าหลักหลัง login)
  - แสดง subscription tier ที่ใช้อยู่
  - countdown วันที่เหลือใน trial/subscription
  - Sebastian Chat quota (ใช้ไปกี่ครั้ง/เหลือกี่ครั้ง)
  - summary card: จำนวน Business Class ที่ตั้งไว้
  - summary card: พื้นที่ที่ครอบคลุม
  - summary card: จำนวน keywords
  - summary card: งานที่ Sebastian หามาให้วันนี้
  - recent job matches feed (5 รายการล่าสุด พร้อม deadline chip)
  - ปุ่ม upgrade

  PAGE 3 — Business Class Setup
  - เพิ่ม/ลบ/แก้ไข class ธุรกิจ (เช่น คอนกรีตผสมเสร็จ, ท่ออัดแรง, รับเหมาก่อสร้าง)
  - แต่ละ class มีการตั้งค่าแยกกัน:
    - Geographic Mode 1: เลือกจังหวัด (multi-select), อำเภอ, ตำบล
    - Geographic Mode 2: กรอก GPS โรงงาน + ระบุรัศมีกี่ km → ระบบคำนวณพื้นที่ครอบคลุมให้อัตโนมัติ
    - Keywords: default keywords ตาม class + เพิ่ม/ลบ custom keywords เอง

  PAGE 4 — Company Profile & Settings
  - ชื่อบริษัท
  - เบอร์โทร
  - Email
  - ช่วงมูลค่างานที่รับ (min-max budget range)
  - toggle: เป็น SME ไหม (แต้มต่อ 7.5% ในการประมูล)
  - toggle: สินค้า Made in Thailand (MIT) ไหม
  - เวลาแจ้งเตือน (06:00 ทุกวัน)

  PAGE 5 — Package & Upgrade
  5 tiers:
  - Trial (30 วัน ฟรี): Sebastian Chat 30 ครั้ง/เดือน
  - Starter (1,500 บาท/เดือน): Sebastian Chat 15 ครั้ง/เดือน
  - Standard (1,800 บาท/เดือน): Sebastian Chat 30 ครั้ง/เดือน
  - Premium (2,100 บาท/เดือน): Sebastian Chat ไม่จำกัด
  - Ultra Luxury (3,500 บาท/เดือน): Sebastian Chat ไม่จำกัด + วิเคราะห์หลายงานพร้อมกัน + สร้าง Dashboard สรุปได้

  ทุก tier เข้าถึงข้อมูลเหมือนกันหมด ต่างกันแค่ Sebastian Chat และ capability
  Payment: PromptPay QR

  === TARGET USER ===
  เจ้าของบริษัทก่อสร้าง SME ไทย ใช้ LINE เป็นหลัก

  === TECH NOTE ===
  Next.js + Tailwind, deploy บน Vercel
  ภาษาไทยทั้งหมด

</pasted_text>

<!-- The user explicitly selected the following skills for this project, as attachments to their message. These are not optional context — they define how you work. Use them. -->
<attached-skill name="Hi-fi design">
Create a high-fidelity, polished design. Follow the instructions about design in your system prompt, particularly the 'How to do design work' section. Use the design_canvas starter component, or make a full-bleed prototype and offer options via Tweaks.
</attached-skill>

<attached-skill name="Interactive prototype">
Create a fully interactive prototype with realistic state management and transitions. Use React useState/useEffect for dynamic behavior. Include hover states, click interactions, form validation, animated transitions, and multi-step navigation flows. It should feel like a real working app, not a static mockup.
</attached-skill>


<system-reminder>Auto-injected reminder (ignore if not relevant): do not recreate copyrighted or branded UI unless the user's email domain matches that company. Create original designs instead.</system-reminder>

## Assistant

_[tool: questions_v2]_

ผมจะออกแบบ master system website ให้ครับ ก่อนเริ่มขอถามคำถามเพื่อทำความเข้าใจสไตล์และทิศทางการออกแบบนะครับ

หมายเหตุสำคัญ: ผมจะออกแบบโดยใช้แรงบันดาลใจจาก "butler aesthetic" (Victorian, formal, refined) แต่จะไม่ recreate ตัวละครหรือ visual elements ที่ copyrighted จาก Black Butler โดยตรงครับ — จะสร้าง original design ที่ให้ความรู้สึก "พ่อบ้านสุภาพชน" ด้วยตัวเอง

## User

Questions answered:
- aesthetic_direction: Explore a few options (แสดงหลายแบบใน tweaks)
- tone_of_voice: ผสม — formal Thai butler ที่ฟังเข้าใจง่าย
- primary_focus: ทุกหน้าเท่ากัน
- interactivity_level: Click-through prototype ทุกปุ่มทำงาน (สลับ tier, เพิ่ม class, multi-step)
- variations_wanted: สีโทน (dark / light / mixed), Layout dashboard (card grid vs list vs split), Navigation (sidebar vs top tabs), Typography (serif หนัก vs modern mix)
- iconography: ผสม — heraldic accent + lucide icons ในเนื้อหา
- geographic_ui: ใช้พร้อมกันได้ — แต่ละ class เก็บทั้งจังหวัด list + รัศมี
- package_default: Trial (active 14 วันเหลือ)
- must_have_details: ให้แทนลูกค้าว่าท่าน และ Mobile First

## Assistant

_[tool: update_todos]_

_[tool: copy_starter_component]_

ขอบคุณครับท่าน เริ่มสร้างได้เลย ผมจะตั้งทิศทางการออกแบบเป็น **"Manor Master System"** — original butler aesthetic ที่ไม่อ้างอิงตัวละครหรือ branded elements จาก IP ใดๆ ใช้:

- **โทนสี:** Ink & Cream (deep ink #0E0D0B / cream #F4EDDE / champagne gold) + 2 ทางเลือกใน tweaks
- **Typography:** Cormorant Garamond (เซริฟหนัก ใช้กับ heading) + IBM Plex Sans Thai (body) + Plex Mono accent
- **Heraldic accents:** monogram "S" + ornamental dividers + crest แบบเรียบง่าย
- **Tone:** Sebastian เรียกผู้ใช้ว่า "ท่าน" formal-but-warm
- **Mobile-first:** layout 390px เป็นหลัก + responsive ขึ้น tablet/desktop

มาเริ่มกันเลย

_[tool: read_file]_

_[tool: write_file]_

_[tool: write_file]_

_[tool: write_file]_

_[tool: write_file]_

_[tool: write_file]_

_[tool: write_file]_

_[tool: write_file]_

_[tool: write_file]_

_[tool: write_file]_

_[tool: grep]_

_[tool: read_file]_

_[tool: write_file]_

_[tool: show_html]_

_[tool: show_html]_

_[tool: get_webview_logs]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: get_webview_logs]_

_[tool: save_screenshot]_

_[tool: save_screenshot]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: show_html]_

_[tool: sleep]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: done]_

Let me try with the user's view to confirm rendering, then commit:

_[tool: screenshot_user_view]_

_[tool: eval_js_user_view]_

_[tool: eval_js_user_view]_

_[tool: eval_js_user_view]_

_[tool: eval_js_user_view]_

_[tool: eval_js_user_view]_

_[tool: screenshot_user_view]_

_[tool: str_replace_edit]_

The page renders beautifully — the issue is `backdrop-filter` confusing html-to-image. Let me fix the CSS:

_[tool: str_replace_edit]_

_[tool: grep]_

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

_[tool: show_html]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: str_replace_edit]_

_[tool: show_html]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: str_replace_edit]_

Looks great! Let me fix the "อัปเกรด" button wrapping and capture more screens.

_[tool: multi_screenshot]_

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

_[tool: show_html]_

_[tool: multi_screenshot]_

_[tool: str_replace_edit]_

_[tool: multi_screenshot]_

_[tool: done]_

_[tool: snip]_

_[tool: update_todos]_

_[tool: fork_verifier_agent]_

เสร็จเรียบร้อยครับท่าน — **Sebastian · Manor Master System** พร้อมใช้งานแล้ว

## สิ่งที่ได้
**5 หน้าหลัก ทำงานได้จริง:**
- **Login** — เห็น tier comparison ก่อน + ปุ่ม LINE
- **Company World** — tier banner + countdown, quota ring, summary cards, recent matches feed พร้อม Sebastian note
- **Business Class** — เพิ่ม/แก้ไข/ลบ class, geographic mode 1+2 ใช้พร้อมกัน, keyword editor + restore defaults
- **Company Profile** — budget range slider, SME/MIT toggles, time picker
- **Package & Upgrade** — เปรียบเทียบ 5 tiers, monthly/annual toggle, PromptPay QR flow → success

**Tweaks (มุมขวาล่าง — toggle จาก toolbar):**
- **Theme** — Ink (Dark) / Manor (Light) / Twilight (Mixed)
- **Typography** — Heavy Serif / Modern Mix
- **Dashboard Layout** — Grid / List / Split
- **Navigation** — Bottom / Top Tabs / Sidebar
- **Tier** — สลับ Trial → Ultra Luxury เพื่อดูเอฟเฟกต์

**ทิศทางการออกแบบ:**
- Original "butler aesthetic" — heraldic crest "S" + ornamental dividers (ไม่ใช้ branded IP)
- Tone: Sebastian เรียกผู้ใช้ว่า "ท่าน" สุภาพแต่เข้าใจง่าย
- Mobile-first 480px, responsive ขึ้น desktop

**Caveats:**
- PromptPay QR เป็น placeholder (ลายตาราง) — จะใช้จริงต้อง integrate PromptPay API
- ข้อมูลทุกอย่างเป็น mock state ใน React useState — ไม่ persist ลง localStorage/server
- การคำนวณรัศมีพื้นที่ครอบคลุมเป็น approximation π·r²รับทราบครับท่าน — Verifier ตรวจสอบเสร็จแล้วโดยไม่พบประเด็นที่ต้องแก้ไข ระบบพร้อมให้ท่านเล่นและปรับผ่าน Tweaks ได้เลยครับ

## User

Apply drawing

## Assistant

_[tool: str_replace_edit]_

รับทราบครับท่าน — เพิ่มการแบ่ง Recent Matches เป็น 2 ประเภท: **"กำลังประมูล"** กับ **"Pre-TOR"** (ร่าง TOR ก่อนประกาศประมูลจริง — ช่วยให้ท่านเตรียมตัวล่วงหน้า)Now update the World page to add the tab switcher and Pre-TOR card variant:

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

Now add the `FeedTab` and `PretorCard` components:

_[tool: str_replace_edit]_

_[tool: done]_

_[tool: multi_screenshot]_

_[tool: str_replace_edit]_

_[tool: show_html]_

_[tool: multi_screenshot]_

แบ่งเรียบร้อยครับท่าน — Recent Matches ตอนนี้มี 2 tabs:

- **กำลังประมูล [5]** — งานประมูลที่เปิดรับยื่นข้อเสนอ พร้อม deadline countdown
- **Pre-TOR [3]** — ร่าง TOR ที่ยังอยู่ในขั้นรับฟังความเห็น พร้อม:
  - **Phase indicator** 4 ขั้น: ร่าง → รับฟัง → สรุป → ประมูล
  - **ปิดรับความเห็น** (กี่วันเหลือ)
  - **คาดประมูล** (เดือนที่คาดว่าจะประกาศประมูลจริง)
  - งบประมาณ + class + keywords ที่ตรง

Sebastian's note ยังปรับข้อความให้เหมาะกับ tab ที่เลือกด้วยครับ — สลับไปดู Pre-TOR Sebastian จะแนะนำว่าท่านสามารถส่งความเห็นได้ก่อนเพื่อเตรียมตัวล่วงหน้า

## User

Apply drawing

## Assistant

_[tool: snip]_

รับทราบครับ — จะเพิ่มช่องวาง Google Maps link ที่ระบบจะดึงพิกัด lat/lng ออกมาให้อัตโนมัติ

_[tool: read_file]_

_[tool: str_replace_edit]_

Now add the `GoogleMapsPicker` component:

_[tool: str_replace_edit]_

_[tool: done]_

_[tool: multi_screenshot]_

_[tool: multi_screenshot]_

_[tool: eval_js]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: eval_js]_

Parser works for all common URL patterns:
- ✓ `@13.6843,100.4129` → ดึงพิกัดได้
- ✓ `?q=13.7563,100.5018` → ดึงพิกัดได้
- ✓ `!3d13.7466!4d100.4929` (place URLs) → ดึงพิกัดได้
- ✓ พิกัดเปลือย `13.7563, 100.5018` → ใส่ได้เลย
- ⚠️ `goo.gl/maps/...` (ลิงก์สั้น) → แสดงข้อความให้ผู้ใช้คัดลอกลิงก์เต็ม (เพราะ short URL ต้อง follow redirect ไม่มี API ให้ทำใน browser)

ฟีเจอร์เพิ่มเติมที่ใส่ไว้:
- **ปุ่ม "วางจาก clipboard"** — กดทีเดียวอ่าน clipboard มาเลย (ถ้า browser ให้ permission)
- **Live feedback** — แสดง ✓ "ดึงพิกัดได้แล้ว: 13.6843°N · 100.4129°E" ทันทีที่วาง URL
- **Place name extraction** — ดึงชื่อสถานที่จาก `/place/...` ใน URL มาใส่ในช่องชื่อโรงงานให้ด้วย
- **คำแนะนำสำหรับลิงก์สั้น** — กรณีวาง goo.gl จะบอกให้เปิดใน Maps แล้วคัดลอก URL เต็ม

## User

ฉันอยากให้หลังจากการกรอก พื้นที่ครอบคลุมเสร็จ สมมุติว่ากรอบพื้นที่ครอบคลุมเป็นจังหวัดนครพนม พอเลื่อนลงมาข้างล่าง ก็จะมีชื่ออำเภอและชื่อตำบลให้ติ๊ก และถ้าหากว่าใช้โหมดสอง ก็จะมีชื่ออำเภอและชื่อตำบลให้ติ๊กเหมือนกัน แต่ว่าถ้าเป็นโหมดสองจะมีการติ๊กมาให้ก่อนหน้านั้นแล้วตามรัศมีที่กรอก ถ้าหากว่าลูกค้าอยากติ๊กเพิ่มหรืออยากติ๊กออก ก็ให้ทำเพิ่มได้เลย และฉันอยากให้หลังจาก set up class แล้ว อยากให้มีปุ่มบันทึกไว้ด้านล่างด้วย

## User

Apply drawing

## Assistant

_[tool: write_file]_

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

รับทราบครับท่าน — จะแก้ 3 จุด:
1. **เพิ่มจังหวัดให้ครบ 77 จังหวัด** (ตอนนี้มีแค่ 30)
2. **เพิ่มชื่ออำเภอ/ตำบลให้ติ๊ก** หลังเลือกจังหวัด + auto-tick ตามรัศมีใน Mode 2
3. **ปุ่มบันทึก** ที่ลอยอยู่ด้านล่างให้ชัดเจน

เริ่มจากสร้างฐานข้อมูลอำเภอ/ตำบล (เน้นจริงๆ ที่นครพนม + บึงกาฬ ตามที่ท่านทดสอบ):

_[tool: str_replace_edit]_

Now update the data model and GeoEditor to support district/tambon selection:

_[tool: grep]_

_[tool: read_file]_

_[tool: read_file]_

_[tool: str_replace_edit]_

Now build the DistrictPicker UI and integrate it into GeoEditor:

_[tool: read_file]_

_[tool: read_file]_

_[tool: grep]_

_[tool: read_file]_

_[tool: write_file]_

_[tool: str_replace_edit]_

_[tool: done]_

The page-classes.jsx expects `THAI_GEO` with nested tambons + `distanceKm`. Let me restructure thai-admin.jsx to match:

_[tool: multi_screenshot]_

_[tool: multi_screenshot]_

_[tool: eval_js]_

_[tool: screenshot]_

_[tool: eval_js]_

_[tool: screenshot]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: eval_js]_

_[tool: eval_js_user_view]_

_[tool: screenshot_user_view]_

All wiring works — 46 district rows present in DOM, save summary card with "บันทึกพื้นที่ครอบคลุม" button at bottom. Here's what's in:

**1. จังหวัดครบ 77 จังหวัด** — รวมนครพนม, บึงกาฬ, สกลนคร, มุกดาหาร, หนองคาย ฯลฯ ครบทุกภาค

**2. District/Tambon picker ใหม่ใต้ Mode 1+2:**
- หลังเลือกจังหวัด → ปรากฏการ์ด "อำเภอ / ตำบล" พร้อมรายการอำเภอ (เช่น นครพนม 12 อำเภอ, บึงกาฬ 8 อำเภอ — ข้อมูลจริง)
- แต่ละจังหวัดยุบ/ขยายได้, ปุ่ม "ทั้งหมด/ล้าง" เลือกเร็ว
- แต่ละอำเภอกดเปิดได้ → เห็นตำบลให้ติ๊กเป็น chip
- Checkbox มีสถานะ indeterminate (เลือกบางตำบล) → แสดงเส้นกลาง

**3. Mode 2 (รัศมี) auto-tick:**
- เมื่อ GPS + รัศมี เปลี่ยน → ระบบคำนวณด้วย haversine distance หา district/tambon ภายในรัศมี → auto-tick ให้
- District ที่อยู่ในรัศมีมี chip **"ในรัศมี XX กม."** สีเขียว
- Tambon ที่อยู่ในรัศมีแต่ยังไม่ติ๊ก มีจุดเขียวเล็กๆ บอก
- User ติ๊กเพิ่ม/ลบได้อิสระ (merge แบบ non-destructive)

**4. ปุ่มบันทึก:** ใต้ทุกอย่าง — กิลด์เฟรมสีทอง summary stats (จังหวัด/อำเภอ/ตำบล) + ปุ่ม **"บันทึกพื้นที่ครอบคลุม"** ใหญ่ → กดแล้ว show success state ก่อน close drawer

ลองเปิดคลาส "คอนกรีตผสมเสร็จ" → เลื่อนลงจะเห็น picker ใหม่นี้ครับท่าน

## User

ฉันอยากให้ตอนบันทึกแล้ว มันไม่เด้งกลับไปหน้า Class เหมือนเดิม แค่เขียนว่า "บันทึกเสร็จแล้ว" เฉยๆ ก็ได้. แล้วก็อยู่ที่หน้าเดิม

## Assistant

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

_[tool: read_file]_

_[tool: grep]_

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

_[tool: read_file]_

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

_[tool: done]_

เรียบร้อยครับท่าน — แก้แล้ว 3 จุด:

- **"บันทึกพื้นที่ครอบคลุม"** (geo tab) → กดแล้วเปลี่ยนเป็นกรอบสีทอง "บันทึกเสร็จแล้ว" 2.4 วินาที แล้วกลับเป็นปุ่มเดิม — **ไม่ปิด drawer**
- **"บันทึก Keywords"** → กดแล้วปุ่มเปลี่ยนเป็น "บันทึกเสร็จแล้ว" 2.2 วินาที **ไม่ปิด drawer**
- **"บันทึกชื่อ Class"** → กดแล้วปุ่มเปลี่ยนเป็น "บันทึกเสร็จแล้ว" 2.2 วินาที **ไม่ปิด drawer**

ส่วน footer button เปลี่ยนจาก "บันทึก" (ที่เคยปิด drawer) เป็น **"← กลับไปหน้า Class"** เพื่อให้ความหมายชัด — ปุ่มนี้ใช้สำหรับ "เสร็จแล้ว ปิด" อย่างเดียว (และยังกดปุ่ม chevron ซ้ายบนเพื่อปิดได้เหมือนเดิม)

