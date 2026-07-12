/**
 * customers.ts — Server-side helpers for customer data via the BMS engine API
 * (bms_api.py on the VPS → SQLite bms_customers.db, the single source of truth).
 *
 * Replaces the old Google Sheets backend (googleapis): killed serverless cold-start
 * and the silent Sheets↔SQLite divergence. See
 * docs/superpowers/plans/2026-06-30-portal-customer-store-unify.md
 */

const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

// ── Types ────────────────────────────────────────────────────────────────────
// Kept identical to the previous Sheets-backed shape so no call site changes.

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
  provinces: string[]; // จังหวัดที่ subscribe จริง (subscription_provinces — source of truth ของพื้นที่ครอบคลุม)
}

// Engine returns a subset; fill the rest with empty strings to keep the shape.
// Province/keyword config lives in notes.classes (province-first) + subscription_provinces,
// not as flat columns — so จังหวัด/อำเภอ/keywords are surfaced as "" here.
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
}

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
  };
}

function headers(): HeadersInit {
  return { "Content-Type": "application/json", "X-BMS-Secret": BMS_SECRET };
}

// ── Reads / writes ─────────────────────────────────────────────────────────────

export async function getCustomerByLineId(lineUserId: string): Promise<Customer | null> {
  if (!lineUserId) return null;
  const url = `${BMS_API_URL}/api/portal/customer?line_user_id=${encodeURIComponent(lineUserId)}`;
  const res = await fetch(url, { headers: headers(), cache: "no-store" });
  if (!res.ok) throw new Error(`engine GET customer failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; customer: EngineCustomer | null };
  return data.customer ? toCustomer(data.customer) : null;
}

export async function upsertCustomer(
  data: Partial<Customer> & { line_user_id: string },
): Promise<{ customer: Customer; isNew: boolean }> {
  const lineId = data.line_user_id.trim();
  if (!lineId) throw new Error("line_user_id required");

  // Only profile + notes are persisted by the engine; province/keyword config
  // is carried inside notes.classes (province-first scope).
  const body: Record<string, string> = { line_user_id: lineId };
  for (const k of ["display_name", "email", "phone", "notes"] as const) {
    const v = data[k];
    if (v != null && v !== "") body[k] = v;
  }

  const res = await fetch(`${BMS_API_URL}/api/portal/customer`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`engine POST customer failed: ${res.status}`);
  const out = (await res.json()) as { ok: boolean; is_new: boolean };

  const customer = (await getCustomerByLineId(lineId)) ?? toCustomer({ line_user_id: lineId });
  return { customer, isNew: out.is_new };
}
