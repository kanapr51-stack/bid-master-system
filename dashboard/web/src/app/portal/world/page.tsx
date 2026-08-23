import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { requireOnboarding } from '@/lib/onboarding';
import { parsePortalNotes, getTierId, getTier } from '@/lib/portal-data';
import { getPortalJobs, getDiscoverJobs, type JobGroups, type DiscoverGroups } from '@/lib/portal-jobs';
import { getAllJobs, type SentJob } from '@/lib/portal-all-jobs';
import { getLastScanAt } from '@/lib/portal-status';
import { WorldClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function WorldPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  const customer = await requireOnboarding(session.lineUserId);

  const notes = parsePortalNotes(customer?.notes ?? '');
  const tierId = getTierId(customer ?? { status: 'trial', notes: '' });
  const tier = getTier(tierId);
  const classes = notes.classes ?? [];

  // N+226.2: 4 คำขอนี้ไม่พึ่งกัน — ยิงพร้อมกันแทน await ทีละอันตามลำดับ (เดิมรวม latency
  // ทุกตัว ตอนนี้เหลือแค่ตัวที่ช้าสุด) engine ล่มรายตัว = fail-open เหมือนเดิม (ไม่ทั้งหน้าพัง)
  const [jobGroupsR, discoverGroupsR, allJobsR, lastScanAtR] = await Promise.allSettled([
    getPortalJobs(session.lineUserId),
    getDiscoverJobs(session.lineUserId),
    // N+221: ต้องดึง jobs[] จริงด้วย (ไม่ใช่แค่ count) — ใช้หา "งานที่มีการเคลื่อนไหววันนี้"
    // (followed=true + sent_at=วันนี้) สำหรับ Part 2 ของ "งานใหม่วันนี้"
    getAllJobs(session.lineUserId, 200),
    getLastScanAt(),
  ]);

  const jobGroups: JobGroups = jobGroupsR.status === 'fulfilled'
    ? jobGroupsR.value : { won: [], prelim: [], bidding: [], pre: [], cancelled: [] };

  const discoverGroups: DiscoverGroups = discoverGroupsR.status === 'fulfilled'
    ? discoverGroupsR.value : { biddable: [], planning: [] };

  let allNotifiedCount = 0;
  let allNotifiedNewToday = 0;
  let allNotifiedJobs: SentJob[] = [];
  if (allJobsR.status === 'fulfilled') {
    allNotifiedCount = allJobsR.value.count;
    allNotifiedNewToday = allJobsR.value.newToday;
    allNotifiedJobs = allJobsR.value.jobs;
  }

  // วันที่วันนี้ตามเขตเวลาไทย — ใช้ตัดสิน "เคลื่อนไหววันนี้" (ตรงเกณฑ์เดียวกับ new_today ฝั่ง engine)
  const todayBkk = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Bangkok' }).format(new Date());

  const lastScanAt = lastScanAtR.status === 'fulfilled' ? lastScanAtR.value : '';

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
        notifyTime: notes.notifyTime ?? '23:00',
      }}
      tierId={tierId}
      chatUsed={notes.chatUsed ?? 0}
      chatQuota={tier.chatQuota}
      daysLeft={daysLeft}
      expiryLabel={expiryLabel}
      classes={classes}
      subscribedProvinces={customer?.provinces ?? []}
      jobGroups={jobGroups}
      discoverGroups={discoverGroups}
      allNotifiedCount={allNotifiedCount}
      allNotifiedNewToday={allNotifiedNewToday}
      allNotifiedJobs={allNotifiedJobs}
      todayBkk={todayBkk}
      lastScanAt={lastScanAt}
    />
  );
}
