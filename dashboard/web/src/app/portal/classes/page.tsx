import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getCustomerByLineId } from '@/lib/customers';
import { parsePortalNotes } from '@/lib/portal-data';
import { ClassesClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function ClassesPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  let customer = null;
  try { customer = await getCustomerByLineId(session.lineUserId); } catch { /* ignore */ }

  const notes = parsePortalNotes(customer?.notes ?? '');

  return (
    <ClassesClient
      lineUserId={session.lineUserId}
      initialClasses={notes.classes ?? []}
    />
  );
}
