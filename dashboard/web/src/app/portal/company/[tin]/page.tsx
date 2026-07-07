import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getCompanyDetail, type CompanyDetail } from '@/lib/portal-company-detail';
import { CompanyDetailClient } from './_client';

export const dynamic = 'force-dynamic';

type Search = { from?: string; proc?: string; area_ids?: string; area_label?: string };

export default async function CompanyDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ tin: string }>;
  searchParams: Promise<Search>;
}) {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  const { tin } = await params;
  const sp = await searchParams;
  const proc = ['bid', 'specific', 'other'].includes(sp.proc ?? '') ? sp.proc! : 'all';

  let detail: CompanyDetail | null = null;
  let engineDown = false;
  try {
    detail = await getCompanyDetail(session.lineUserId, tin, {
      proc,
      areaIds: sp.area_ids ?? '',
      areaLabel: sp.area_label ?? '',
    });
  } catch {
    engineDown = true; // engine ล่ม — แสดงการ์ดแจ้ง ไม่ crash
  }

  return (
    <CompanyDetailClient
      tin={tin}
      detail={detail}
      engineDown={engineDown}
      from={sp.from ?? ''}
      proc={proc}
      areaIds={sp.area_ids ?? ''}
      areaLabel={sp.area_label ?? ''}
    />
  );
}
