'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TopBar, Chip, Icons, Diamond } from '../_ui';
import type { AllJobs, SentJob, SentJobStage } from '@/lib/portal-all-jobs';

// ป้าย stage — ชุดเดียวกับ STAGE_META ของ world
const STAGE_LABEL: Record<SentJobStage, { icon: string; label: string; tone: 'gold' | 'emerald' | 'wine' | 'outline' }> = {
  bidding: { icon: '🔵', label: 'ยื่นซองได้', tone: 'gold' },
  prelim: { icon: '🟡', label: 'รอผล', tone: 'outline' },
  won: { icon: '🏆', label: 'รู้ผลแล้ว', tone: 'emerald' },
  pre: { icon: '⚪', label: 'รับฟังคำวิจารณ์', tone: 'outline' },
  cancelled: { icon: '❌', label: 'ยกเลิก', tone: 'wine' },
};

// ลำดับ chip กรอง phase — ตาม lifecycle เดียวกับ STAGE_META ของ world
const STAGE_ORDER: SentJobStage[] = ['bidding', 'prelim', 'won', 'pre', 'cancelled'];

function fmtBaht(n: number | null | undefined): string {
  if (!n) return '';
  return n.toLocaleString('th-TH');
}

function fmtSentDate(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: '2-digit' });
}

function SentJobCard({ job }: { job: SentJob }) {
  const meta = STAGE_LABEL[job.stage] ?? STAGE_LABEL.bidding;
  return (
    <Link href={`/portal/job/${encodeURIComponent(job.project_id)}`} style={{ textDecoration: 'none', color: 'inherit' }}>
      <div className="p-card" style={{ padding: 14, borderColor: job.starred ? 'var(--accent-deep)' : 'var(--border)', background: job.starred ? 'var(--gold-glow)' : 'var(--surface)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
          <div className="p-display" style={{ fontSize: 15, lineHeight: 1.35, minWidth: 0 }}>
            {job.starred && <span style={{ color: 'var(--accent)' }}>★ </span>}{job.name}
          </div>
          <Chip tone={meta.tone}>{meta.icon} {meta.label}</Chip>
        </div>
        <div className="p-fg-mute" style={{ fontSize: 12, marginTop: 8, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          {job.province && <span>📍 {job.province}</span>}
          {job.budget > 0 && <span>💰 {fmtBaht(job.budget)} บาท</span>}
          <span className="p-fg-dim">🔔 ส่งเมื่อ {fmtSentDate(job.sent_at)}</span>
        </div>
      </div>
    </Link>
  );
}

export function AllJobsClient({ data, engineDown }: { data: AllJobs | null; engineDown: boolean }) {
  const router = useRouter();
  const [q, setQ] = useState('');
  // ติ๊กกรอง phase: ว่าง = เห็นทั้งหมด, ติ๊ก ≥1 = เฉพาะ stage ที่ติ๊ก (OR)
  const [stages, setStages] = useState<Set<SentJobStage>>(new Set());

  const stageCounts = useMemo(() => {
    const counts = new Map<SentJobStage, number>();
    for (const j of data?.jobs ?? []) counts.set(j.stage, (counts.get(j.stage) ?? 0) + 1);
    return counts;
  }, [data]);

  const toggleStage = (s: SentJobStage) => setStages(prev => {
    const next = new Set(prev);
    if (next.has(s)) next.delete(s); else next.add(s);
    return next;
  });

  const jobs = useMemo(() => {
    const all = data?.jobs ?? [];
    const needle = q.trim().toLowerCase();
    return all.filter(j =>
      (stages.size === 0 || stages.has(j.stage)) &&
      (!needle || j.name.toLowerCase().includes(needle) || j.province.toLowerCase().includes(needle)));
  }, [data, q, stages]);
  const filtering = q.trim() !== '' || stages.size > 0;

  if (!data) {
    return (
      <div className="p-enter">
        <TopBar title="งานทั้งหมด" subtitle="All Notified Jobs" onLeft={() => router.push('/portal/world')} />
        <div className="p-page p-page-topbar">
          <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
              {engineDown ? 'ดึงข้อมูลไม่ได้ชั่วคราว — ลองใหม่อีกครั้งครับ' : 'ยังไม่มีข้อมูล'}
            </div>
            <Link href="/portal/world">
              <button className="p-btn p-btn-ghost" style={{ marginTop: 14, height: 36, padding: '0 16px', fontSize: 13 }}>
                กลับหน้าหลัก
              </button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-enter">
      <TopBar
        title="งานทั้งหมด"
        subtitle="ทุกงานที่ระบบเคยส่งให้ท่าน"
        onLeft={() => router.push('/portal/world')}
        right={<Chip tone="gold" icon={<Diamond size={5} />}>{data.count} งาน</Chip>}
      />

      <div className="p-page p-page-topbar">
        {/* ค้นหา */}
        <div style={{ position: 'relative', marginBottom: 14 }}>
          <span style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--fg-dim)', display: 'flex' }}>
            <Icons.Search size={15} />
          </span>
          <input
            className="p-input"
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="ค้นหาจากชื่องาน หรือจังหวัด…"
            style={{ width: '100%', paddingLeft: 36 }}
          />
        </div>

        {/* ติ๊กกรอง phase */}
        {data.jobs.length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
            {STAGE_ORDER.filter(s => (stageCounts.get(s) ?? 0) > 0).map(s => {
              const meta = STAGE_LABEL[s];
              const on = stages.has(s);
              return (
                <button
                  key={s}
                  onClick={() => toggleStage(s)}
                  className={`p-chip ${on ? 'p-chip-gold' : 'p-chip-outline'}`}
                  style={{ cursor: 'pointer', fontFamily: 'inherit' }}
                  aria-pressed={on}
                >
                  {on && '✓ '}{meta.icon} {meta.label} <span style={{ opacity: 0.7 }}>{stageCounts.get(s)}</span>
                </button>
              );
            })}
          </div>
        )}

        {data.jobs.length === 0 ? (
          <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
              ยังไม่มีงานที่ระบบส่งให้ — เมื่อมีงานใหม่ตรงเงื่อนไข จะขึ้นที่นี่พร้อมแจ้งใน LINE ครับ
            </div>
          </div>
        ) : jobs.length === 0 ? (
          <div className="p-card" style={{ textAlign: 'center', padding: 22 }}>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 13.5 }}>
              {q.trim() ? <>ไม่พบงานที่ตรงกับ &quot;{q}&quot;</> : 'ไม่พบงานที่ตรงกับเงื่อนไขที่ติ๊กไว้'}
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {filtering && (
              <div className="p-fg-dim" style={{ fontSize: 11.5 }}>พบ {jobs.length} จาก {data.jobs.length} งาน</div>
            )}
            {jobs.map(job => <SentJobCard key={job.project_id} job={job} />)}
          </div>
        )}
      </div>
    </div>
  );
}
