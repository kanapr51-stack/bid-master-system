import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getCustomerByLineId } from '@/lib/customers';
import { parsePortalNotes } from '@/lib/portal-data';
import { nextOnboardingPath } from '@/lib/onboarding';
import { NotificationsClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function NotificationsPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  let customer = null;
  let engineOk = true;
  try { customer = await getCustomerByLineId(session.lineUserId); } catch { engineOk = false; }

  const notes = parsePortalNotes(customer?.notes ?? '');
  const nextStep = engineOk ? nextOnboardingPath(customer) : null; // engine ล่ม — fail-open เหมือน requireOnboarding ห้าม redirect มั่ว
  // ยังไม่ผ่านโปรไฟล์/ตั้งค่า ห้ามข้ามมาหน้านี้ — ผ่านครบแล้ว (nextStep=null) ก็ยังเข้าดูซ้ำได้ (ไม่ใช่ onboarding แล้ว)
  if (nextStep === '/portal/profile' || nextStep === '/portal/settings') redirect(nextStep);

  return <NotificationsClient notes={notes} />;
}
