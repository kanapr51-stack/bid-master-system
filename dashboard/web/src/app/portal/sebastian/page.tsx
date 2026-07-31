import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { requireOnboarding } from '@/lib/onboarding';
import { getSebastianFeed, type SebastianFeed } from '@/lib/portal-sebastian-feed';
import { SebastianClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function SebastianPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  await requireOnboarding(session.lineUserId);

  let data: SebastianFeed | null = null;
  let engineDown = false;
  try {
    data = await getSebastianFeed(session.lineUserId);
  } catch {
    engineDown = true; // engine ล่ม — แสดงการ์ดแจ้ง ไม่ crash
  }

  return <SebastianClient data={data} engineDown={engineDown} />;
}
