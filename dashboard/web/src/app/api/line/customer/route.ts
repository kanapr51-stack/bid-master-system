import { NextResponse } from "next/server";
import { getCustomerByLineId, upsertCustomer } from "@/lib/customers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/line/customer?line_user_id=Uxxx
 *   → returns customer data (or null)
 */
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const lineId = searchParams.get("line_user_id");
  if (!lineId) {
    return NextResponse.json({ ok: false, error: "line_user_id required" }, { status: 400 });
  }
  try {
    const customer = await getCustomerByLineId(lineId);
    return NextResponse.json({ ok: true, customer });
  } catch (e) {
    console.error("[customer GET]", e);
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 500 },
    );
  }
}

/**
 * POST /api/line/customer
 *   body: { line_user_id, display_name?, จังหวัด?, อำเภอ?, keywords?, email?, phone? }
 *   → upserts the customer, returns updated record
 */
export async function POST(req: Request) {
  try {
    const body = await req.json();
    if (!body.line_user_id) {
      return NextResponse.json({ ok: false, error: "line_user_id required" }, { status: 400 });
    }
    const { customer, isNew } = await upsertCustomer(body);
    return NextResponse.json({ ok: true, customer, isNew });
  } catch (e) {
    console.error("[customer POST]", e);
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 500 },
    );
  }
}
