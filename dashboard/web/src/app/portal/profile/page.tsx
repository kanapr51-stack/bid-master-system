import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getCustomerByLineId } from '@/lib/customers';
import { parsePortalNotes } from '@/lib/portal-data';
import { ProfileClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function ProfilePage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  let customer = null;
  try { customer = await getCustomerByLineId(session.lineUserId); } catch { /* ignore */ }

  const notes = parsePortalNotes(customer?.notes ?? '');

  let daysLeft = 30;
  let expiryLabel = '';
  if (customer?.expires_at) {
    const expiry = new Date(customer.expires_at);
    daysLeft = Math.max(0, Math.ceil((expiry.getTime() - Date.now()) / 86400000));
    expiryLabel = expiry.toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  return (
    <ProfileClient
      lineUserId={session.lineUserId}
      initialProfile={{
        companyName: customer?.display_name || session.displayName || '',
        phone: customer?.phone || '',
        email: customer?.email || '',
        budgetMin: notes.budgetMin ?? 1,
        budgetMax: notes.budgetMax ?? 50,
        isSME: notes.isSME ?? false,
        isMIT: notes.isMIT ?? false,
        notifyTime: notes.notifyTime ?? '06:00',
      }}
      classCount={notes.classes?.length ?? 0}
      registeredAt={customer?.registered_at?.slice(0, 10) ?? ''}
      tierId={notes.tierId ?? (customer?.status === 'trial' ? 'trial' : 'standard')}
      daysLeft={daysLeft}
      expiryLabel={expiryLabel}
    />
  );
}
