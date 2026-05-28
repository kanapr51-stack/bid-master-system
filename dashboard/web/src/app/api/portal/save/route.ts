/**
 * POST /api/portal/save — persist portal notes (classes, tier, settings)
 * Body: PortalNotes JSON
 */
import { NextRequest, NextResponse } from 'next/server';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { upsertCustomer } from '@/lib/customers';
import { encodePortalNotes, type PortalNotes } from '@/lib/portal-data';

export async function POST(req: NextRequest) {
  const sessionValue = req.cookies.get(COOKIE_NAME)?.value;
  if (!sessionValue) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const session = await parseSessionCookie(sessionValue);
  if (!session) return NextResponse.json({ error: 'Invalid session' }, { status: 401 });

  let body: PortalNotes;
  try {
    body = await req.json() as PortalNotes;
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  try {
    await upsertCustomer({
      line_user_id: session.lineUserId,
      notes: encodePortalNotes(body),
    });
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error('[/api/portal/save]', err);
    return NextResponse.json({ error: 'Save failed' }, { status: 500 });
  }
}
