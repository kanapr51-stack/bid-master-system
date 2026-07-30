import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { requireOnboarding } from '@/lib/onboarding';
import { parsePortalNotes, getTierId } from '@/lib/portal-data';
import { PackagesClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function PackagesPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  const customer = await requireOnboarding(session.lineUserId);

  const notes = parsePortalNotes(customer?.notes ?? '');
  const tierId = getTierId(customer ?? { status: 'trial', notes: '' });

  let daysLeft = 30;
  let expiryLabel = 'ทดลองใช้';
  if (customer?.expires_at) {
    const expiry = new Date(customer.expires_at);
    daysLeft = Math.max(0, Math.ceil((expiry.getTime() - Date.now()) / 86400000));
    expiryLabel = expiry.toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  return (
    <PackagesClient
      lineUserId={session.lineUserId}
      currentTierId={tierId}
      daysLeft={daysLeft}
      expiryLabel={expiryLabel}
    />
  );
}
