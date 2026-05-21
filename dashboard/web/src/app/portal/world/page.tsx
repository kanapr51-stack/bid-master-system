import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getCustomerByLineId } from '@/lib/customers';
import { parsePortalNotes, getTierId, getTier, SEED_JOBS } from '@/lib/portal-data';
import { WorldClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function WorldPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  let customer = null;
  try {
    customer = await getCustomerByLineId(session.lineUserId);
  } catch { /* Sheets unavailable — use defaults */ }

  const notes = parsePortalNotes(customer?.notes ?? '');
  const tierId = getTierId(customer ?? { status: 'trial', notes: '' });
  const tier = getTier(tierId);
  const classes = notes.classes ?? [];

  // Calculate trial days left
  let daysLeft = 30;
  let expiryLabel = '';
  if (customer?.expires_at) {
    const expiry = new Date(customer.expires_at);
    daysLeft = Math.max(0, Math.ceil((expiry.getTime() - Date.now()) / 86400000));
    expiryLabel = expiry.toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  return (
    <WorldClient
      profile={{
        companyName: customer?.display_name || session.displayName || 'บริษัทของท่าน',
        phone: customer?.phone || '',
        email: customer?.email || '',
        budgetMin: notes.budgetMin ?? 1,
        budgetMax: notes.budgetMax ?? 50,
        isSME: notes.isSME ?? false,
        isMIT: notes.isMIT ?? false,
        notifyTime: notes.notifyTime ?? '06:00',
      }}
      tierId={tierId}
      chatUsed={notes.chatUsed ?? 0}
      chatQuota={tier.chatQuota}
      daysLeft={daysLeft}
      expiryLabel={expiryLabel}
      classes={classes}
      jobs={SEED_JOBS}
      initialStarred={notes.starred ?? []}
    />
  );
}
