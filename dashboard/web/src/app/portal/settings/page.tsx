import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getCustomerByLineId } from '@/lib/customers';
import { parsePortalNotes } from '@/lib/portal-data';
import { SettingsClient } from './_client';

export const dynamic = 'force-dynamic';

// N+199: หน้าตั้งค่าแบน (แทนระบบบริษัท /portal/classes) — พื้นที่ read-only + คำค้น + ช่วงงบ
export default async function SettingsPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  let customer = null;
  try { customer = await getCustomerByLineId(session.lineUserId); } catch { /* engine unavailable */ }

  const notes = parsePortalNotes(customer?.notes ?? '');
  const cls = (notes.classes ?? [])[0];
  const keywords = [...new Set([...(cls?.keywords ?? []), ...(cls?.defaultKeywords ?? [])])];

  return (
    <SettingsClient
      provinces={customer?.provinces ?? []}
      initialKeywords={keywords}
      initialBudgetMin={cls?.budgetMinBaht ?? 0}
      initialBudgetMax={cls?.budgetMaxBaht ?? 0}
      initialIsSME={notes.isSME ?? false}
      initialIsMIT={notes.isMIT ?? false}
      initialNotifyTime={notes.notifyTime ?? '20:00'} // default ตรง engine (Sebastian_Daily_User_Summary.DEFAULT_NOTIFY)
      notes={notes}
    />
  );
}
