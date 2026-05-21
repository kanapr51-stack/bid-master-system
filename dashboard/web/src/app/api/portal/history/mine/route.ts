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
    } catch { /* fallback */ }
  }
  if (!companyName) return NextResponse.json({ jobs: [], total: 0 });

  const result = await searchOwnBids(companyName);
  return NextResponse.json(result);
}
