import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { requireOnboarding } from '@/lib/onboarding';
import { getJobDetail, type JobDetail } from '@/lib/portal-job-detail';
import { JobDetailClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function JobDetailPage({ params }: { params: Promise<{ pid: string }> }) {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  await requireOnboarding(session.lineUserId);

  const { pid } = await params;

  let detail: JobDetail | null = null;
  let engineDown = false;
  try {
    detail = await getJobDetail(session.lineUserId, pid);
  } catch {
    engineDown = true; // engine ล่ม — แสดงการ์ดแจ้ง ไม่ crash
  }

  return <JobDetailClient pid={pid} detail={detail} engineDown={engineDown} />;
}
