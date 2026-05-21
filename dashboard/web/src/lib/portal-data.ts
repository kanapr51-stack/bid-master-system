/**
 * portal-data.ts — Types, constants and Sheets helpers for the Customer Portal
 */

// ── Types ────────────────────────────────────────────────────────────────────

export interface BusinessClassGeo {
  mode: 'province' | 'radius' | 'both';
  provinces: string[];
  districts: string[];  // "Province::District"
  tambons: string[];    // "Province::District::Tambon"
  gps: { lat: number; lng: number; label: string } | null;
  radiusKm: number;
}

export interface CompanyFile {
  name: string;
  url: string;
  uploadedAt: string;
  sizeBytes: number;
}

export interface BusinessClass {
  id: string;
  name: string;
  color: string;
  geo: BusinessClassGeo;
  keywords: string[];
  defaultKeywords: string[];
  budgetMinBaht?: number;
  budgetMaxBaht?: number;
  isSME?: boolean;
  isMIT?: boolean;
  notifyTime?: string;
  files?: CompanyFile[];
}

export interface PortalProfile {
  companyName: string;
  phone: string;
  email: string;
  budgetMin: number;
  budgetMax: number;
  isSME: boolean;
  isMIT: boolean;
  notifyTime: string;
}

export interface PortalJob {
  id: string;
  stage: 'bidding' | 'pretor';
  title: string;
  agency: string;
  budget: number;
  deadline?: string;
  daysLeft?: number;
  pretorPhase?: string;
  pretorEnd?: string;
  daysToComment?: number;
  expectedBidDate?: string;
  matchedClassId?: string;
  matchedKeywords: string[];
  distance?: number;
  sme: boolean;
  mit: boolean;
}

// Stored as JSON in the customer "notes" field
export interface PortalNotes {
  classes?: BusinessClass[];
  tierId?: string;
  chatUsed?: number;
  budgetMin?: number;
  budgetMax?: number;
  isSME?: boolean;
  isMIT?: boolean;
  notifyTime?: string;
  starred?: string[];
}

export interface Tier {
  id: string;
  name: string;
  nameTh: string;
  price: number;
  priceLabel: string;
  chatQuota: number; // -1 = unlimited
  chatLabel: string;
  period?: string;
  perks: string[];
  note: string;
  popular?: boolean;
}

// ── Constants ─────────────────────────────────────────────────────────────────

export const TIERS: Tier[] = [
  {
    id: 'trial', name: 'Trial', nameTh: 'ทดลองใช้',
    price: 0, priceLabel: 'ฟรี 30 วัน',
    chatQuota: 30, chatLabel: '30 ครั้ง / เดือน', period: '30 วันแรก',
    perks: ['เข้าถึงข้อมูลงานประมูลครบ', 'ตั้ง Business Class ได้ไม่จำกัด', 'Sebastian Chat 30 ครั้ง / เดือน', 'แจ้งเตือนงานประจำวัน'],
    note: 'เริ่มต้นสำหรับท่านที่ยังไม่เคยใช้บริการ',
  },
  {
    id: 'starter', name: 'Starter', nameTh: 'เริ่มต้น',
    price: 1500, priceLabel: '1,500 ฿/เดือน',
    chatQuota: 15, chatLabel: '15 ครั้ง / เดือน',
    perks: ['เข้าถึงข้อมูลงานประมูลครบ', 'Sebastian Chat 15 ครั้ง / เดือน', 'แจ้งเตือนงานทุกเช้า', 'รองรับหลาย Business Class'],
    note: 'เหมาะกับท่านที่ใช้แชทไม่บ่อย',
  },
  {
    id: 'standard', name: 'Standard', nameTh: 'มาตรฐาน',
    price: 1800, priceLabel: '1,800 ฿/เดือน',
    chatQuota: 30, chatLabel: '30 ครั้ง / เดือน',
    perks: ['ทุกอย่างใน Starter', 'Sebastian Chat 30 ครั้ง / เดือน', 'วิเคราะห์งานคู่แข่งเบื้องต้น'],
    note: 'ขายดี — สมดุลระหว่างราคาและความสามารถ',
    popular: true,
  },
  {
    id: 'premium', name: 'Premium', nameTh: 'พรีเมียม',
    price: 2100, priceLabel: '2,100 ฿/เดือน',
    chatQuota: -1, chatLabel: 'ไม่จำกัด',
    perks: ['ทุกอย่างใน Standard', 'Sebastian Chat ไม่จำกัด', 'อ่าน/สรุปเอกสารประมูล', 'วิเคราะห์คู่แข่งเชิงลึก'],
    note: 'สำหรับท่านที่ต้องการคุยกับ Sebastian ตลอดเวลา',
  },
  {
    id: 'ultra', name: 'Ultra Luxury', nameTh: 'อัลตร้า ลักชัวรี่',
    price: 3500, priceLabel: '3,500 ฿/เดือน',
    chatQuota: -1, chatLabel: 'ไม่จำกัด',
    perks: ['ทุกอย่างใน Premium', 'วิเคราะห์งานหลายงานพร้อมกัน', 'สร้าง Dashboard สรุปได้', 'Sebastian จัดเอกสารให้อัตโนมัติ', 'Priority support 24 ชม.'],
    note: 'บริการเต็มรูปแบบ ราวกับมีพ่อบ้านส่วนตัว',
  },
];

export const THAI_PROVINCES: string[] = [
  'กระบี่', 'กรุงเทพมหานคร', 'กาญจนบุรี', 'กาฬสินธุ์', 'กำแพงเพชร', 'ขอนแก่น', 'จันทบุรี', 'ฉะเชิงเทรา',
  'ชลบุรี', 'ชัยนาท', 'ชัยภูมิ', 'ชุมพร', 'เชียงราย', 'เชียงใหม่', 'ตรัง', 'ตราด', 'ตาก', 'นครนายก',
  'นครปฐม', 'นครพนม', 'นครราชสีมา', 'นครศรีธรรมราช', 'นครสวรรค์', 'นนทบุรี', 'นราธิวาส', 'น่าน',
  'บึงกาฬ', 'บุรีรัมย์', 'ปทุมธานี', 'ประจวบคีรีขันธ์', 'ปราจีนบุรี', 'ปัตตานี', 'พระนครศรีอยุธยา',
  'พะเยา', 'พังงา', 'พัทลุง', 'พิจิตร', 'พิษณุโลก', 'เพชรบุรี', 'เพชรบูรณ์', 'แพร่', 'ภูเก็ต',
  'มหาสารคาม', 'มุกดาหาร', 'แม่ฮ่องสอน', 'ยโสธร', 'ยะลา', 'ร้อยเอ็ด', 'ระนอง', 'ระยอง', 'ราชบุรี',
  'ลพบุรี', 'ลำปาง', 'ลำพูน', 'เลย', 'ศรีสะเกษ', 'สกลนคร', 'สงขลา', 'สตูล', 'สมุทรปราการ',
  'สมุทรสงคราม', 'สมุทรสาคร', 'สระแก้ว', 'สระบุรี', 'สิงห์บุรี', 'สุโขทัย', 'สุพรรณบุรี', 'สุราษฎร์ธานี',
  'สุรินทร์', 'หนองคาย', 'หนองบัวลำภู', 'อ่างทอง', 'อำนาจเจริญ', 'อุดรธานี', 'อุตรดิตถ์', 'อุทัยธานี',
  'อุบลราชธานี',
];

export const DEFAULT_KEYWORDS_BY_CLASS: Record<string, string[]> = {
  'คอนกรีตผสมเสร็จ': ['คอนกรีตผสมเสร็จ', 'Ready-mixed Concrete', 'RMC', 'คอนกรีต', 'ปูนซีเมนต์'],
  'ท่ออัดแรง': ['ท่ออัดแรง', 'ท่อคอนกรีตอัดแรง', 'Prestressed Concrete Pipe', 'ท่อระบายน้ำ', 'คสล.'],
  'รับเหมาก่อสร้าง': ['รับเหมาก่อสร้าง', 'ก่อสร้างอาคาร', 'งานโยธา', 'ปรับปรุงอาคาร', 'ต่อเติม'],
  'งานโยธา': ['งานโยธา', 'ก่อสร้างถนน', 'ท่อระบายน้ำ', 'ดิน', 'เกรด', 'ลูกรัง', 'ถนนลาดยาง'],
  'งานไฟฟ้า': ['งานไฟฟ้า', 'ระบบไฟฟ้า', 'ติดตั้งไฟฟ้า', 'สายไฟ', 'ตู้ไฟ', 'หม้อแปลง'],
  'งานเหล็ก': ['งานเหล็ก', 'โครงเหล็ก', 'เหล็กก่อสร้าง', 'เหล็กเส้น', 'เหล็กแผ่น'],
  'งานประปา': ['ประปา', 'ระบบน้ำ', 'ท่อประปา', 'ระบบน้ำดื่ม', 'สูบน้ำ'],
  'งานสะพาน': ['สะพาน', 'คสล.', 'ข้ามคลอง', 'สะพานคอนกรีต', 'รางระบาย'],
  'อุปกรณ์การแพทย์': ['อุปกรณ์การแพทย์', 'เครื่องมือแพทย์', 'Medical Equipment', 'ครุภัณฑ์การแพทย์'],
  'คอมพิวเตอร์และ IT': ['คอมพิวเตอร์', 'Server', 'Network', 'Software', 'ระบบสารสนเทศ', 'ระบบคอมพิวเตอร์'],
  'เฟอร์นิเจอร์และครุภัณฑ์': ['เฟอร์นิเจอร์', 'ครุภัณฑ์', 'โต๊ะ', 'เก้าอี้', 'ตู้เอกสาร'],
  'รถยนต์และยานพาหนะ': ['รถยนต์', 'รถบรรทุก', 'ยานพาหนะ', 'รถกระบะ', 'รถตู้'],
};

export const CLASS_SUGGESTIONS = Object.keys(DEFAULT_KEYWORDS_BY_CLASS);

// District/Tambon data is in a separate file to keep this module lean.
// Import THAI_GEO directly from '@/app/portal/thai-geo-data' in components that need it.

// ── Helpers ───────────────────────────────────────────────────────────────────

export function parsePortalNotes(notesStr: string): PortalNotes {
  if (!notesStr?.trim()) return {};
  try {
    const parsed = JSON.parse(notesStr);
    if (typeof parsed === 'object' && parsed !== null) return parsed as PortalNotes;
  } catch { /* ignore parse errors */ }
  return {};
}

export function encodePortalNotes(notes: PortalNotes): string {
  return JSON.stringify(notes);
}

export function getTierId(customer: { status: string; notes: string }): string {
  const notes = parsePortalNotes(customer.notes);
  if (notes.tierId) return notes.tierId;
  if (customer.status === 'trial') return 'trial';
  if (customer.status === 'active') return 'standard';
  return 'trial';
}

export function getTier(tierId: string): Tier {
  return TIERS.find(t => t.id === tierId) ?? TIERS[0];
}

export function distanceKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

// Seed jobs — replaced by real pipeline data in Phase 2
export const SEED_JOBS: PortalJob[] = [
  { id: 'j1', stage: 'bidding', title: 'ก่อสร้างปรับปรุงถนนคอนกรีต ซอยเทศบาล 4', agency: 'เทศบาลตำบลบางบ่อ จ.สมุทรปราการ', budget: 8.5, daysLeft: 9, matchedKeywords: ['คอนกรีตผสมเสร็จ', 'RMC'], distance: 12, sme: true, mit: true },
  { id: 'j2', stage: 'bidding', title: 'จ้างเหมาก่อสร้างระบบระบายน้ำ ท่ออัดแรง', agency: 'อบจ.นครปฐม', budget: 24.2, daysLeft: 16, matchedKeywords: ['ท่ออัดแรง', 'ท่อคอนกรีตอัดแรง'], distance: 48, sme: true, mit: true },
  { id: 'j3', stage: 'bidding', title: 'ปรับปรุงอาคารสำนักงาน 3 ชั้น', agency: 'ศาลากลางจังหวัดนนทบุรี', budget: 14.0, daysLeft: 4, matchedKeywords: ['รับเหมาก่อสร้าง', 'ปรับปรุงอาคาร'], distance: 22, sme: false, mit: true },
  { id: 'j4', stage: 'bidding', title: 'ก่อสร้างพื้นคอนกรีตลานจอดรถ 4,200 ตร.ม.', agency: 'การประปาส่วนภูมิภาค สาขาปทุมธานี', budget: 6.8, daysLeft: 12, matchedKeywords: ['คอนกรีตผสมเสร็จ'], distance: 28, sme: true, mit: true },
  { id: 'p1', stage: 'pretor', title: 'ก่อสร้างถนนคอนกรีตเสริมเหล็ก สายบ้านโคก-บ้านดอน', agency: 'อบต.บางพลีน้อย จ.สมุทรปราการ', budget: 11.2, pretorPhase: 'รับฟังความเห็น', daysToComment: 7, expectedBidDate: 'มิ.ย. 2569', matchedKeywords: ['คอนกรีตผสมเสร็จ', 'ถนนคอนกรีต'], distance: 22, sme: true, mit: true },
  { id: 'p2', stage: 'pretor', title: 'ก่อสร้างระบบระบายน้ำพร้อมท่อคอนกรีตอัดแรง ระยะที่ 2', agency: 'เทศบาลนครนนทบุรี', budget: 45.8, pretorPhase: 'ร่าง TOR ครั้งที่ 1', daysToComment: 11, expectedBidDate: 'ปลายมิ.ย. 2569', matchedKeywords: ['ท่อคอนกรีตอัดแรง'], distance: 35, sme: true, mit: true },
];
