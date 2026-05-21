import { NextRequest, NextResponse } from 'next/server';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { queryCompetitorProfile, searchCompetitors } from '@/lib/bid-history';

export async function GET(req: NextRequest) {
  const sessionValue = req.cookies.get(COOKIE_NAME)?.value;
  if (!sessionValue) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const session = await parseSessionCookie(sessionValue);
  if (!session) return NextResponse.json({ error: 'Invalid session' }, { status: 401 });

  const { searchParams } = new URL(req.url);
  const tin = searchParams.get('tin');
  const q = searchParams.get('q');

  if (tin) {
    const data = await queryCompetitorProfile(tin);
    if ('error' in data) return NextResponse.json(data, { status: 404 });
    return NextResponse.json(data);
  }
  if (q && q.length >= 2) {
    const data = await searchCompetitors(q);
    return NextResponse.json({ results: data });
  }
  return NextResponse.json({ error: 'Provide tin or q param (min 2 chars)' }, { status: 400 });
}
