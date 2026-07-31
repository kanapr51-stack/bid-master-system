/**
 * portal-day-groups.ts — จัดกลุ่มรายการตามวัน (เวลาไทย) ใช้ร่วมกันระหว่าง
 * /portal/jobs (card list) และ /portal/sebastian (chat feed)
 */
export const BKK_TZ = 'Asia/Bangkok';

export function dayKey(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return 'unknown';
  return d.toLocaleDateString('en-CA', { timeZone: BKK_TZ });
}

export function dayLabel(key: string, todayKey: string, yesterdayKey: string): string {
  if (key === 'unknown') return 'ไม่ระบุวัน';
  const thai = new Date(`${key}T00:00:00+07:00`).toLocaleDateString('th-TH', {
    day: 'numeric', month: 'short', year: '2-digit', timeZone: BKK_TZ,
  });
  if (key === todayKey) return `วันนี้ · ${thai}`;
  if (key === yesterdayKey) return `เมื่อวาน · ${thai}`;
  return thai;
}

export function getTodayKey(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: BKK_TZ });
}

export function getYesterdayKey(): string {
  return new Date(Date.now() - 86400000).toLocaleDateString('en-CA', { timeZone: BKK_TZ });
}
