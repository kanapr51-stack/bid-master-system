/**
 * portal-status.ts — สถานะระบบทั่วไป (ไม่ผูก customer เฉพาะราย) สำหรับ badge เล็กๆ ในหน้า portal
 */
const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

export async function getLastScanAt(): Promise<string> {
  const url = `${BMS_API_URL}/api/portal/last-scan`;
  const res = await fetch(url, { headers: { "X-BMS-Secret": BMS_SECRET }, cache: "no-store" });
  if (!res.ok) throw new Error(`engine GET last-scan failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; last_scan_at?: string };
  return data.last_scan_at ?? "";
}
