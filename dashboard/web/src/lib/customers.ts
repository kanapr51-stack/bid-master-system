/**
 * customers.ts — Server-side helpers for "customers" sheet via Sheets API
 * (mirrors scripts/customers_db.py)
 */
import { google } from "googleapis";

const SPREADSHEET_ID = "1gz7qLDIWphDhqxLf8Pxm08_cPmNb_IXTDvyxm6uThps";
const SHEET_NAME = "customers";

export const HEADERS = [
  "line_user_id",
  "display_name",
  "email",
  "phone",
  "จังหวัด",
  "อำเภอ",
  "keywords",
  "status",
  "registered_at",
  "expires_at",
  "last_active_at",
  "notes",
] as const;

export type CustomerField = (typeof HEADERS)[number];

export interface Customer {
  line_user_id: string;
  display_name: string;
  email: string;
  phone: string;
  จังหวัด: string;
  อำเภอ: string;
  keywords: string;
  status: string;
  registered_at: string;
  expires_at: string;
  last_active_at: string;
  notes: string;
}

let _sheets: ReturnType<typeof google.sheets> | null = null;

function getSheetsClient() {
  if (_sheets) return _sheets;
  const credsJson = process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
  if (!credsJson) {
    throw new Error("GOOGLE_SERVICE_ACCOUNT_JSON env var not set");
  }
  // dotenv strips outer quotes and converts \n → actual newlines.
  // JSON.parse rejects literal newlines inside string literals, so restore them.
  let creds;
  try {
    creds = JSON.parse(credsJson);
  } catch {
    creds = JSON.parse(credsJson.replace(/\n/g, '\\n'));
  }
  const auth = new google.auth.GoogleAuth({
    credentials: creds,
    scopes: ["https://www.googleapis.com/auth/spreadsheets"],
  });
  _sheets = google.sheets({ version: "v4", auth });
  return _sheets;
}

function rowToCustomer(row: string[]): Customer {
  const out = {} as Record<string, string>;
  HEADERS.forEach((h, i) => {
    out[h] = row[i] ?? "";
  });
  return out as unknown as Customer;
}

function customerToRow(c: Partial<Customer>): string[] {
  return HEADERS.map((h) => (c as Record<string, string>)[h] ?? "");
}

export async function listCustomers(): Promise<Customer[]> {
  const sheets = getSheetsClient();
  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: SPREADSHEET_ID,
    range: `${SHEET_NAME}!A2:L`,
  });
  const rows = res.data.values ?? [];
  return rows
    .filter((r) => r && r[0])
    .map((r) => rowToCustomer(r as string[]));
}

export async function getCustomerByLineId(lineUserId: string): Promise<Customer | null> {
  if (!lineUserId) return null;
  const all = await listCustomers();
  return all.find((c) => c.line_user_id === lineUserId) ?? null;
}

export async function upsertCustomer(
  data: Partial<Customer> & { line_user_id: string },
): Promise<{ customer: Customer; isNew: boolean }> {
  const lineId = data.line_user_id.trim();
  if (!lineId) throw new Error("line_user_id required");

  const sheets = getSheetsClient();
  const now = new Date().toISOString().slice(0, 19);

  const res = await sheets.spreadsheets.values.get({
    spreadsheetId: SPREADSHEET_ID,
    range: `${SHEET_NAME}!A2:L`,
  });
  const rows = (res.data.values ?? []) as string[][];

  for (let i = 0; i < rows.length; i++) {
    if (rows[i] && rows[i][0] === lineId) {
      const existing = rowToCustomer(rows[i]);
      const merged: Customer = {
        ...existing,
        ...Object.fromEntries(
          Object.entries(data).filter(([, v]) => v != null && v !== ""),
        ),
        line_user_id: lineId,
        last_active_at: now,
      } as Customer;
      const rowNum = i + 2;
      await sheets.spreadsheets.values.update({
        spreadsheetId: SPREADSHEET_ID,
        range: `${SHEET_NAME}!A${rowNum}:L${rowNum}`,
        valueInputOption: "USER_ENTERED",
        requestBody: { values: [customerToRow(merged)] },
      });
      return { customer: merged, isNew: false };
    }
  }

  // New customer
  const trialExpiry = new Date();
  trialExpiry.setDate(trialExpiry.getDate() + 14);

  const newCustomer: Customer = {
    line_user_id: lineId,
    display_name: data.display_name ?? "",
    email: data.email ?? "",
    phone: data.phone ?? "",
    จังหวัด: data.จังหวัด ?? "",
    อำเภอ: data.อำเภอ ?? "",
    keywords: data.keywords ?? "",
    status: data.status ?? "trial",
    registered_at: data.registered_at ?? now,
    expires_at: data.expires_at ?? trialExpiry.toISOString().slice(0, 19),
    last_active_at: now,
    notes: data.notes ?? "",
  };

  await sheets.spreadsheets.values.append({
    spreadsheetId: SPREADSHEET_ID,
    range: `${SHEET_NAME}!A:L`,
    valueInputOption: "USER_ENTERED",
    requestBody: { values: [customerToRow(newCustomer)] },
  });

  return { customer: newCustomer, isNew: true };
}
