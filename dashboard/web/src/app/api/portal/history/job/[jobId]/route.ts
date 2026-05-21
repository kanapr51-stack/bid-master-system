import { NextRequest, NextResponse } from 'next/server';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { queryJobBidders } from '@/lib/bid-history';

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  const sessionValue = req.cookies.get(COOKIE_NAME)?.value;
  if (!sessionValue) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const session = await parseSessionCookie(sessionValue);
  if (!session) return NextResponse.json({ error: 'Invalid session' }, { status: 401 });

  const { jobId } = await params;
  const data = await queryJobBidders(jobId);
  if ('error' in data) return NextResponse.json(data, { status: 404 });
  return NextResponse.json(data);
}
