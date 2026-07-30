import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { getCustomerByLineId } from '@/lib/customers';
import { parsePortalNotes } from '@/lib/portal-data';
import { nextOnboardingPath } from '@/lib/onboarding';
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
  let engineOk = true;
  try { customer = await getCustomerByLineId(session.lineUserId); } catch { engineOk = false; }

  const notes = parsePortalNotes(customer?.notes ?? '');
  const nextStep = engineOk ? nextOnboardingPath(customer) : null; // engine ล่ม — fail-open เหมือน requireOnboarding ห้าม redirect มั่ว
  if (nextStep === '/portal/profile') redirect('/portal/profile'); // ยังกรอกโปรไฟล์ไม่ครบ ห้ามข้ามมาตั้งค่า
  const isOnboarding = nextStep === '/portal/settings';
  const cls = (notes.classes ?? [])[0];
  const keywords = [...new Set([...(cls?.keywords ?? []), ...(cls?.defaultKeywords ?? [])])];

  return (
    <SettingsClient
      isOnboarding={isOnboarding}
      provinces={customer?.provinces ?? []}
      initialKeywords={keywords}
      initialBudgetMin={cls?.budgetMinBaht ?? 0}
      initialBudgetMax={cls?.budgetMaxBaht ?? 0}
      initialIsSME={notes.isSME ?? false}
      initialIsMIT={notes.isMIT ?? false}
      initialNotifyTime={notes.notifyTime ?? '23:00'} // default ตรง engine (Sebastian_Daily_User_Summary.DEFAULT_NOTIFY)
      initialMorningTime={notes.morningNotifyTime ?? '07:30'} // default ตรง engine (notify_schedule.DEFAULT_MORNING)
      notes={notes}
    />
  );
}
