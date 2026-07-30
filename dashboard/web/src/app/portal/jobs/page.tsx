import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { requireOnboarding } from '@/lib/onboarding';
import { getAllJobs, type AllJobs } from '@/lib/portal-all-jobs';
import { AllJobsClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function AllJobsPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  await requireOnboarding(session.lineUserId);

  let data: AllJobs | null = null;
  let engineDown = false;
  try {
    data = await getAllJobs(session.lineUserId);
  } catch {
    engineDown = true; // engine ล่ม — แสดงการ์ดแจ้ง ไม่ crash
  }

  return <AllJobsClient data={data} engineDown={engineDown} />;
}
