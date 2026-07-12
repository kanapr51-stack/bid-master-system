import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getCustomerByLineId } from '@/lib/customers';
import { parsePortalNotes, getTierId } from '@/lib/portal-data';
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
        userName: notes.userName,
        userGmail: notes.userGmail,
        userPhone: notes.userPhone,
        userLineId: notes.userLineId,
      }}
      classes={(notes.classes ?? []).filter(c => c.id !== 'settings')} // N+199.1: ซ่อน hidden class ของหน้าตั้งค่า
      classCount={(notes.classes ?? []).filter(c => c.id !== 'settings').length}
      registeredAt={customer?.registered_at?.slice(0, 10) ?? ''}
      tierId={getTierId(customer ?? { status: 'trial', notes: '' })}
      daysLeft={daysLeft}
      expiryLabel={expiryLabel}
    />
  );
}
