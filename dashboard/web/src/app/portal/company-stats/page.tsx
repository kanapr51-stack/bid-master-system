import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getCustomerByLineId } from '@/lib/customers';
import { parsePortalNotes } from '@/lib/portal-data';
import { CompanyStatsClient } from './_client';

export const dynamic = 'force-dynamic';

interface Props {
  searchParams: Promise<{ classId?: string }>;
}

export default async function CompanyStatsPage({ searchParams }: Props) {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  let customer = null;
  try { customer = await getCustomerByLineId(session.lineUserId); } catch { /* ignore */ }

  const notes = parsePortalNotes(customer?.notes ?? '');
  const params = await searchParams;
  const classId = params.classId ?? '';
  const cls = (notes.classes ?? []).find(c => c.id === classId) ?? null;

  return (
    <CompanyStatsClient
      cls={cls}
      allClasses={notes.classes ?? []}
    />
  );
}
