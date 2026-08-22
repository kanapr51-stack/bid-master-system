'use client';

import { useState } from 'react';
import Link from 'next/link';
import { type BusinessClass, TIERS } from '@/lib/portal-data';
import type { PortalProfile } from '@/lib/portal-data';
import type { JobGroups, JobStage, TrackedJob, DiscoverGroups, DiscoverJob } from '@/lib/portal-jobs';
import type { SentJob } from '@/lib/portal-all-jobs';
import { TopBar, Chip, Icons, Diamond } from '../_ui';
import PushNotifyBadge from '@/components/PushNotifyBadge';

// Sebastian Chat ยังไม่มีของจริง (LINE เป็นเมนู keyword, ไม่มีตัวนับ chatUsed)
// — ซ่อนการ์ด quota จนกว่าจะสร้างเสร็จ ค่อยเปิด flag นี้
const SEBASTIAN_CHAT_LIVE = false;

// ── Quota Ring ────────────────────────────────────────────────────────────────

function QuotaRing({ pct, unlimited }: { pct: number; unlimited: boolean }) {
  const r = 26, c = 2 * Math.PI * r;
  const dash = unlimited ? c : c * (pct / 100);
  return (
    <div style={{ width: 64, height: 64, position: 'relative' }}>
      <svg width="64" height="64" viewBox="0 0 64 64" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="32" cy="32" r={r} stroke="var(--border)" strokeWidth="4" fill="none" />
        <circle cx="32" cy="32" r={r} stroke="var(--accent)" strokeWidth="4" fill="none"
          strokeDasharray={`${dash} ${c}`} strokeLinecap="round" />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
        {unlimited ? <Icons.Sparkles size={22} /> : <span className="p-display" style={{ fontSize: 15 }}>{pct}%</span>}
      </div>
    </div>
  );
}

// ── Summary Card ──────────────────────────────────────────────────────────────

interface TabSegment {
  key: string;
  icon: React.ReactNode;
  label: string;
  value: number;
  active?: boolean;
  badge?: string;
  href?: string;
  onClick?: () => void;
}

function SummaryTabBar({ starredCount, trackedCount, allCount, allNewToday, view, onSelect }: {
  starredCount: number; trackedCount: number; allCount: number; allNewToday: number;
  view: 'starred' | 'tracked' | null; onSelect: (v: 'starred' | 'tracked') => void;
}) {
  const segments: TabSegment[] = [];
  if (starredCount > 0) {
    segments.push({ key: 'starred', icon: <span style={{ fontSize: 13 }}>★</span>, label: 'งานที่สนใจ', value: starredCount, active: view === 'starred', onClick: () => onSelect('starred') });
  }
  segments.push({ key: 'tracked', icon: <Icons.Bell size={13} />, label: 'งานที่ติดตาม', value: trackedCount, active: view === 'tracked', onClick: () => onSelect('tracked') });
  if (allCount > 0) {
    segments.push({ key: 'all', icon: <Icons.Doc size={13} />, label: 'งานทั้งหมด', value: allCount, href: '/portal/jobs', badge: allNewToday > 0 ? `New+${allNewToday}` : undefined });
  }

  return (
    <div className="p-card" style={{ display: 'flex', padding: 0, overflow: 'hidden' }}>
      {segments.map((seg, i) => {
        const lit = seg.active;
        const inner = (
          <div style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, minWidth: 0,
            padding: '11px 6px', borderRight: i < segments.length - 1 ? '1px solid var(--border)' : 'none',
            background: lit ? 'var(--gold-glow)' : 'transparent', cursor: seg.href || seg.onClick ? 'pointer' : 'default',
          }}>
            <span style={{ display: 'flex', color: lit ? 'var(--accent)' : 'var(--fg-mute)' }}>{seg.icon}</span>
            <span className="p-display" style={{ fontSize: 17, color: lit ? 'var(--accent)' : 'inherit', lineHeight: 1 }}>{seg.value}</span>
            <span className="p-fg-mute p-mono" style={{ fontSize: 10.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{seg.label}</span>
            {seg.badge && (
              <span className="p-mono" style={{ fontSize: 9.5, fontWeight: 600, color: 'var(--accent)', background: 'var(--gold-glow)', border: '1px solid var(--accent-deep)', borderRadius: 999, padding: '0 5px', lineHeight: 1.5 }}>
                {seg.badge}
              </span>
            )}
          </div>
        );
        if (seg.href) return <Link key={seg.key} href={seg.href} style={{ textDecoration: 'none', color: 'inherit', flex: 1, display: 'flex', minWidth: 0 }}>{inner}</Link>;
        if (seg.onClick) return <button key={seg.key} onClick={seg.onClick} style={{ all: 'unset', flex: 1, display: 'flex', minWidth: 0 }}>{inner}</button>;
        return <div key={seg.key} style={{ flex: 1, display: 'flex', minWidth: 0 }}>{inner}</div>;
      })}
    </div>
  );
}

// ── helpers ─────────────────────────────────────────────────────────────────

function daysLeftOf(deadline: string): number | null {
  if (!deadline) return null;
  const d = new Date(deadline);
  if (isNaN(d.getTime())) return null;
  return Math.max(0, Math.ceil((d.getTime() - Date.now()) / 86400000));
}

function fmtBaht(n: number | null): string {
  if (!n) return '—';
  return n.toLocaleString('th-TH');
}

const STAGE_META: { key: JobStage; label: string; icon: string }[] = [
  { key: 'bidding', label: 'ยื่นซองได้', icon: '🔵' },
  { key: 'prelim', label: 'รอผล', icon: '🟡' },
  { key: 'won', label: 'รู้ผลแล้ว', icon: '🏆' },
  { key: 'pre', label: 'รับฟังคำวิจารณ์', icon: '⚪' },
  { key: 'cancelled', label: 'ยกเลิก', icon: '❌' },
];

// ── Tracked Job Card ──────────────────────────────────────────────────────────

function TrackedJobCard({ job, stage, starred, onStar, detailHref, followed, onToggleFollow }: { job: TrackedJob; stage: JobStage; starred: boolean; onStar: () => void; detailHref?: string; followed: boolean; onToggleFollow: () => void }) {
  const dl = daysLeftOf(job.deadline);
  const urgency = dl === null ? 'outline' : dl <= 5 ? 'wine' : dl <= 10 ? 'gold' : 'outline';
  const title = <div className="p-display" style={{ fontSize: 15, lineHeight: 1.3 }}>{job.name}</div>;
  return (
    <div className="p-card" style={{ padding: 14, borderColor: starred ? 'var(--accent-deep)' : 'var(--border)', background: starred ? 'var(--gold-glow)' : 'var(--surface)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          {job.location && <div className="p-mono p-fg-mute" style={{ fontSize: 11, letterSpacing: '0.04em', marginBottom: 4 }}>{job.location}</div>}
          {detailHref ? <Link href={detailHref} style={{ textDecoration: 'none', color: 'inherit' }}>{title}</Link> : title}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
          <button onClick={e => { e.stopPropagation(); onStar(); }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: starred ? 'var(--accent)' : 'var(--fg-dim)', fontSize: 18, padding: '0 2px', lineHeight: 1 }}>
            {starred ? '★' : '☆'}
          </button>
          {(stage === 'bidding' || stage === 'prelim') && dl !== null && (
            <Chip tone={urgency} icon={<Icons.Clock size={11} />}>{dl} วัน</Chip>
          )}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 16, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        {job.budget > 0 && (
          <div>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>ราคากลาง</div>
            <div className="p-serif" style={{ fontSize: 16, fontWeight: 500 }}>
              <span className="p-fg-accent">{fmtBaht(job.budget)}</span> <span className="p-fg-dim" style={{ fontSize: 11 }}>บาท</span>
            </div>
          </div>
        )}
        {job.pred_lo && job.pred_hi && (
          <div style={{ paddingLeft: 16, borderLeft: '1px solid var(--line)' }}>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>คาดราคาเสนอ</div>
            <div className="p-serif" style={{ fontSize: 13 }}>{fmtBaht(job.pred_lo)}–{fmtBaht(job.pred_hi)}</div>
          </div>
        )}
        {stage === 'prelim' && job.prelim_low != null && (
          <div style={{ paddingLeft: 16, borderLeft: '1px solid var(--line)' }}>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>ราคาต่ำสุดตอนนี้</div>
            <div className="p-serif" style={{ fontSize: 13 }}>{fmtBaht(job.prelim_low)}{job.prelim_n > 0 && <span className="p-fg-dim"> · {job.prelim_n} ราย</span>}</div>
          </div>
        )}
        {stage === 'won' && job.winner && (
          <div style={{ paddingLeft: 16, borderLeft: '1px solid var(--line)' }}>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>ผู้ชนะ</div>
            <div className="p-serif" style={{ fontSize: 13 }}>{job.winner}{job.winner_disc != null && <span className="p-fg-dim"> · ลด {job.winner_disc}%</span>}</div>
          </div>
        )}
      </div>
      {job.deadline && (stage === 'bidding' || stage === 'prelim') && (
        <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 8 }}>
          ยื่นซอง: {job.deadline}{job.deadline_time ? ` ${job.deadline_time}` : ''}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginTop: 10, flexWrap: 'wrap' }}>
        {detailHref ? (
          <Link href={detailHref} className="p-fg-accent" style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 12.5, textDecoration: 'none' }}>
            ดูรายละเอียด · คู่แข่ง · โอกาสชนะ <Icons.ChevronRight size={12} />
          </Link>
        ) : <span />}
        {/* N+197.2: ยกเลิกติดตามในที่ — การ์ดคงอยู่ ปุ่มสลับเป็น "ติดตาม" ให้กดกลับได้ (หายตอน reload) */}
        <button
          className={`p-btn ${followed ? 'p-btn-ghost' : 'p-btn-primary'}`}
          title={followed ? 'กดเพื่อยกเลิกติดตาม' : 'กดเพื่อติดตาม'}
          onClick={e => { e.stopPropagation(); onToggleFollow(); }}
          style={{ height: 30, padding: '0 12px', fontSize: 12, display: 'flex', alignItems: 'center', gap: 5 }}
        >
          <Icons.Bell size={12} />{followed ? 'ติดตามแล้ว' : 'ติดตาม'}
        </button>
      </div>
    </div>
  );
}

// ── Discover Card ─────────────────────────────────────────────────────────────

function DiscoverCard({ job, following, onFollow, starred, onStar, detailHref }: {
  job: DiscoverJob; following: boolean; onFollow: () => void; starred: boolean; onStar: () => void; detailHref?: string;
}) {
  const dl = daysLeftOf(job.deadline);
  const urgency = dl === null ? 'outline' : dl <= 5 ? 'wine' : dl <= 10 ? 'gold' : 'outline';
  const title = <div className="p-display" style={{ fontSize: 15, lineHeight: 1.3 }}>{job.name}</div>;
  return (
    <div className="p-card" style={{ padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          {job.location && <div className="p-mono p-fg-mute" style={{ fontSize: 11, letterSpacing: '0.04em', marginBottom: 4 }}>{job.location}</div>}
          {detailHref ? <Link href={detailHref} style={{ textDecoration: 'none', color: 'inherit' }}>{title}</Link> : title}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
          <button onClick={e => { e.stopPropagation(); onStar(); }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: starred ? 'var(--accent)' : 'var(--fg-dim)', fontSize: 18, padding: '0 2px', lineHeight: 1 }}>
            {starred ? '★' : '☆'}
          </button>
          {job.stage === 'biddable' && dl !== null && (
            <Chip tone={urgency} icon={<Icons.Clock size={11} />}>{dl} วัน</Chip>
          )}
          {job.stage === 'planning' && <Chip tone="outline">วางแผน</Chip>}
        </div>
      </div>
      {job.matched_keywords.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
          {job.matched_keywords.map(k => <Chip key={k} tone="gold" icon={<Icons.Tag size={10} />}>{k}</Chip>)}
        </div>
      )}
      <div style={{ display: 'flex', gap: 16, marginTop: 10, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        {job.budget > 0 && (
          <div>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>ราคากลาง</div>
            <div className="p-serif" style={{ fontSize: 16, fontWeight: 500 }}>
              <span className="p-fg-accent">{fmtBaht(job.budget)}</span> <span className="p-fg-dim" style={{ fontSize: 11 }}>บาท</span>
            </div>
          </div>
        )}
        <button className="p-btn p-btn-primary" disabled={following} onClick={onFollow}
          style={{ height: 34, padding: '0 14px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icons.Bell size={13} />{following ? 'ติดตามแล้ว' : 'ติดตาม'}
        </button>
      </div>
      {job.deadline && job.stage === 'biddable' && (
        <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 8 }}>
          ยื่นซอง: {job.deadline}{job.deadline_time ? ` ${job.deadline_time}` : ''}
        </div>
      )}
      {detailHref && (
        <Link href={detailHref} className="p-fg-accent" style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 12.5, marginTop: 10, textDecoration: 'none' }}>
          ดูรายละเอียด · คู่แข่ง · โอกาสชนะ <Icons.ChevronRight size={12} />
        </Link>
      )}
    </div>
  );
}

// ── Movement Job Card (N+221) ────────────────────────────────────────────────

function MovementJobCard({ job, starred, onStar, detailHref }: {
  job: SentJob; starred: boolean; onStar: () => void; detailHref?: string;
}) {
  const meta = STAGE_META.find(s => s.key === job.stage);
  const title = <div className="p-display" style={{ fontSize: 15, lineHeight: 1.3 }}>{job.name}</div>;
  return (
    <div className="p-card" style={{ padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          {job.province && <div className="p-mono p-fg-mute" style={{ fontSize: 11, letterSpacing: '0.04em', marginBottom: 4 }}>{job.province}</div>}
          {detailHref ? <Link href={detailHref} style={{ textDecoration: 'none', color: 'inherit' }}>{title}</Link> : title}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
          <button onClick={e => { e.stopPropagation(); onStar(); }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: starred ? 'var(--accent)' : 'var(--fg-dim)', fontSize: 18, padding: '0 2px', lineHeight: 1 }}>
            {starred ? '★' : '☆'}
          </button>
          {meta && <Chip tone="gold">{meta.icon} {meta.label}</Chip>}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 16, marginTop: 10, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        {job.budget > 0 && (
          <div>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>ราคากลาง</div>
            <div className="p-serif" style={{ fontSize: 16, fontWeight: 500 }}>
              <span className="p-fg-accent">{fmtBaht(job.budget)}</span> <span className="p-fg-dim" style={{ fontSize: 11 }}>บาท</span>
            </div>
          </div>
        )}
        {detailHref && (
          <Link href={detailHref} className="p-fg-accent" style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 12.5, textDecoration: 'none' }}>
            ดูรายละเอียด · คู่แข่ง · โอกาสชนะ <Icons.ChevronRight size={12} />
          </Link>
        )}
      </div>
    </div>
  );
}

// ── World Client ──────────────────────────────────────────────────────────────

interface WorldClientProps {
  profile: PortalProfile;
  tierId: string;
  chatUsed: number;
  chatQuota: number;
  daysLeft: number;
  expiryLabel: string;
  classes: BusinessClass[];
  subscribedProvinces: string[];
  jobGroups: JobGroups;
  discoverGroups: DiscoverGroups;
  allNotifiedCount: number;
  allNotifiedNewToday: number;
  allNotifiedJobs: SentJob[];
  todayBkk: string;
}

export function WorldClient({ profile, tierId, chatUsed, chatQuota, daysLeft, expiryLabel, classes, subscribedProvinces, jobGroups, discoverGroups, allNotifiedCount, allNotifiedNewToday, allNotifiedJobs, todayBkk }: WorldClientProps) {
  // หน้า detail ธีม Board B ในเว็บเดียวกัน (เดิมเด้งไปหน้า engine ธีม A ผ่าน board-token)
  const detailHrefOf = (projectId: string) => `/portal/job/${encodeURIComponent(projectId)}`;
  const allJobs = STAGE_META.flatMap(s => jobGroups[s.key]);
  const [starred, setStarred] = useState<Set<string>>(
    () => new Set([
      ...allJobs.filter(j => j.starred).map(j => j.project_id),
      // การ์ด discovery ก็ persist ดาวข้าม reload (engine ส่ง starred มาแล้ว)
      ...[...discoverGroups.biddable, ...discoverGroups.planning].filter(j => j.starred).map(j => j.project_id),
    ]),
  );

  const toggleStar = async (projectId: string) => {
    const prev = starred;
    const next = new Set(prev);
    if (next.has(projectId)) next.delete(projectId); else next.add(projectId);
    setStarred(next);
    try {
      await fetch('/api/portal/star', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId }),
      });
    } catch {
      setStarred(prev); // revert on failure
    }
  };

  const [discover, setDiscover] = useState<DiscoverGroups>(discoverGroups);
  const [following, setFollowing] = useState<Set<string>>(new Set());

  // N+197.2: ยกเลิกติดตามจากบอร์ด tracked — optimistic สองทิศ, revert เมื่อพลาด (pattern /portal/jobs)
  const [unfollowed, setUnfollowed] = useState<Set<string>>(new Set());
  const handleTrackedToggle = async (projectId: string) => {
    const wasFollowed = !unfollowed.has(projectId);
    setUnfollowed(prev => {
      const n = new Set(prev);
      if (wasFollowed) n.add(projectId); else n.delete(projectId);
      return n;
    });
    try {
      const r = await fetch(wasFollowed ? '/api/portal/unfollow' : '/api/portal/follow', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (!r.ok) throw new Error('toggle follow failed');
    } catch {
      setUnfollowed(prev => {
        const n = new Set(prev);
        if (wasFollowed) n.delete(projectId); else n.add(projectId);
        return n;
      });
    }
  };

  // แท็บ "สนใจ"/"ติดตาม" เลือกได้ทีละอย่าง (radio) — ไม่เลือกเลย = ดีฟอลต์ "งานใหม่วันนี้"
  // กดแท็บที่เลือกอยู่ซ้ำ = กลับดีฟอลต์ (N+221)
  const [view, setView] = useState<'starred' | 'tracked' | null>(null);
  const selectView = (v: 'starred' | 'tracked') => setView(prev => (prev === v ? null : v));
  const filterOn = view === 'starred' && starred.size > 0;

  const handleFollow = async (projectId: string) => {
    setFollowing(prev => new Set(prev).add(projectId));
    try {
      const r = await fetch('/api/portal/follow', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectId }),
      });
      if (!r.ok) throw new Error('follow failed');
      // ติดตามสำเร็จ → เอาออกจาก discovery (จะไปโผล่ tracked รอบหน้า)
      setDiscover(prev => ({
        biddable: prev.biddable.filter(j => j.project_id !== projectId),
        planning: prev.planning.filter(j => j.project_id !== projectId),
      }));
    } catch {
      setFollowing(prev => { const n = new Set(prev); n.delete(projectId); return n; });
    }
  };

  const tier = TIERS.find(t => t.id === tierId) || TIERS[0];
  // N+198.1: พื้นที่ครอบคลุม = subscription จริง (แจ้งเตือนตามนี้) union กับที่ตั้งใน classes
  const provincesCount = new Set([...subscribedProvinces, ...classes.flatMap(c => c.geo.provinces)]).size;
  // N+221: "งานที่มีการเคลื่อนไหว" = งานที่ติดตามอยู่แล้ว (followed) ที่สแกน/จับคู่ซ้ำวันนี้
  // (สเตตขยับ เช่น pre→bidding, bidding→prelim, prelim→won) — ไม่ต้องมี field ใหม่ฝั่ง backend
  const movementJobs = allNotifiedJobs.filter(j => j.followed && (j.sent_at || '').slice(0, 10) === todayBkk);
  const isUnlimited = chatQuota === -1;
  const quotaPct = isUnlimited ? 100 : Math.round(((chatQuota - chatUsed) / chatQuota) * 100);

  return (
    <div className="p-enter">
      <TopBar
        title="Company World"
        subtitle={profile.companyName}
        titleExtra={<PushNotifyBadge />}
        right={
          <>
            <Link href="/portal/sebastian" className="p-icon-btn" title="Sebastian"><Icons.Bot size={18} /></Link>
            <Link href="/portal/packages" className="p-icon-btn" title="แพ็กเกจ"><Icons.Crown size={18} /></Link>
          </>
        }
      />

      <div className="p-page p-page-topbar">
        {/* Sebastian quota — ซ่อนจนกว่าฟีเจอร์แชทจะมีจริง (SEBASTIAN_CHAT_LIVE) */}
        {SEBASTIAN_CHAT_LIVE && (
          <div className="p-card" style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 14 }}>
            <QuotaRing pct={quotaPct} unlimited={isUnlimited} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="p-smallcaps p-fg-mute">Sebastian Chat</div>
              <div className="p-display" style={{ fontSize: 22, marginTop: 2 }}>
                {isUnlimited ? 'ไม่จำกัด' : <><span style={{ color: 'var(--accent)' }}>{chatQuota - chatUsed}</span> / {chatQuota}</>}
              </div>
              <div className="p-fg-dim" style={{ fontSize: 11.5, marginTop: 2 }}>
                {isUnlimited ? 'ปรึกษา Sebastian ใน LINE ได้ตลอดเวลา' : `ใช้ไป ${chatUsed} ครั้งเดือนนี้`}
              </div>
            </div>
          </div>
        )}

        {/* Summary tab bar — สนใจ ซ้ายสุด · ติดตาม กลาง · ทั้งหมด ขวาสุด, เลือกได้ทีละอย่าง (N+220/N+221) */}
        <SummaryTabBar
          starredCount={starred.size}
          trackedCount={allJobs.length}
          allCount={allNotifiedCount}
          allNewToday={allNotifiedNewToday}
          view={view}
          onSelect={selectView}
        />

        {/* Tracked jobs by stage — เฉพาะแท็บ "ติดตาม" (ครบ) หรือ "สนใจ" (กรองดาว) (N+221) */}
        {(view === 'tracked' || view === 'starred') && (
          <div style={{ marginTop: 22 }}>
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 10 }}>
              <div>
                <div className="p-smallcaps p-fg-mute">งานที่ท่านติดตาม</div>
                <div className="p-display" style={{ fontSize: 20, marginTop: 2 }}>Tracked Bids</div>
              </div>
              <Chip tone="gold" icon={<Diamond size={5} />}>
                {filterOn ? `★ ${allJobs.filter(j => starred.has(j.project_id)).length} / ${allJobs.length} งาน` : `${allJobs.length} งาน`}
              </Chip>
            </div>

            {allJobs.length === 0 ? (
              <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
                <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
                  ยังไม่มีงานที่ติดตาม — ระบบจะเพิ่มให้เมื่อเจองานตรงพื้นที่/หมวดของท่านครับ
                </div>
              </div>
            ) : filterOn && allJobs.every(j => !starred.has(j.project_id)) ? (
              <div className="p-card" style={{ textAlign: 'center', padding: 22 }}>
                <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 13.5 }}>
                  ไม่มีงานติดดาวในรายการติดตาม — ดาวของท่านอยู่ในส่วน &quot;งานใหม่ที่แมตช์&quot; ด้านล่างครับ
                </div>
              </div>
            ) : (
              STAGE_META.map(({ key, label, icon }) => {
                const jobs = (jobGroups[key] || []).filter(j => !filterOn || starred.has(j.project_id));
                if (jobs.length === 0) return null;
                return (
                  <div key={key} style={{ marginBottom: 18 }}>
                    <div className="p-label" style={{ margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>{icon}</span>{label} <span className="p-fg-dim">({jobs.length})</span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {jobs.map(job => (
                        <TrackedJobCard
                          key={job.project_id}
                          job={job}
                          stage={key}
                          starred={starred.has(job.project_id)}
                          onStar={() => toggleStar(job.project_id)}
                          detailHref={detailHrefOf(job.project_id)}
                          followed={!unfollowed.has(job.project_id)}
                          onToggleFollow={() => handleTrackedToggle(job.project_id)}
                        />
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* Discovery — แท็บ "สนใจ" (กรองดาว) หรือดีฟอลต์ (ไม่เลือกแท็บ, เป็น Part 1 ของ "งานใหม่วันนี้") (N+221) */}
        {(view === null || view === 'starred') && (() => {
          const discoverAll = [...discover.biddable, ...discover.planning]
            .filter(j => !filterOn || starred.has(j.project_id));
          // N+198: ไม่มี keyword = เห็นทั้งจังหวัด — มีพื้นที่ก็พอ ไม่บังคับคำค้น
          const hasPrefs = provincesCount > 0;
          return (
            <>
              {view === null && (
                <div style={{ marginTop: 22, marginBottom: 4 }}>
                  <div className="p-smallcaps p-fg-mute">วันนี้</div>
                  <div className="p-display" style={{ fontSize: 20, marginTop: 2 }}>📅 งานใหม่วันนี้</div>
                </div>
              )}
              <div style={{ marginTop: view === null ? 14 : 26 }}>
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 10 }}>
                  <div>
                    <div className="p-smallcaps p-fg-mute">{view === null ? 'พาร์ท 1' : 'งานใหม่ที่แมตช์'}</div>
                    <div className="p-display" style={{ fontSize: 20, marginTop: 2 }}>
                      {view === null ? '✨ งานใหม่ที่เพิ่งค้นพบ' : '✨ Matched For You'}
                    </div>
                  </div>
                  {discoverAll.length > 0 && <Chip tone="gold" icon={<Diamond size={5} />}>{discoverAll.length} งาน</Chip>}
                </div>
                {!hasPrefs ? (
                  <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
                    <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
                      ตั้งค่าพื้นที่ในหน้า &quot;ตั้งค่า&quot; เพื่อให้ระบบหางานที่ตรงให้ท่านครับ
                    </div>
                    <Link href="/portal/settings"><button className="p-btn p-btn-primary" style={{ marginTop: 12, height: 34, padding: '0 16px', fontSize: 13 }}>ไปตั้งค่า</button></Link>
                  </div>
                ) : discoverAll.length === 0 ? (
                  <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
                    <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
                      {filterOn
                        ? 'ไม่มีงานติดดาวในส่วนนี้ครับ'
                        : 'ยังไม่มีงานใหม่ที่ตรงเกณฑ์วันนี้ — ระบบจะอัปเดตให้เมื่อมีงานเข้าครับ'}
                    </div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {discoverAll.map(job => (
                      <DiscoverCard
                        key={job.project_id}
                        job={job}
                        following={following.has(job.project_id)}
                        onFollow={() => handleFollow(job.project_id)}
                        starred={starred.has(job.project_id)}
                        onStar={() => toggleStar(job.project_id)}
                        detailHref={detailHrefOf(job.project_id)}
                      />
                    ))}
                  </div>
                )}
              </div>
            </>
          );
        })()}

        {/* Movement — Part 2 ของ "งานใหม่วันนี้": งานที่ติดตามอยู่แล้วแต่สเตตขยับวันนี้ (N+221) */}
        {view === null && (
          <div style={{ marginTop: 26 }}>
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 10 }}>
              <div>
                <div className="p-smallcaps p-fg-mute">พาร์ท 2</div>
                <div className="p-display" style={{ fontSize: 20, marginTop: 2 }}>🔄 งานที่มีการเคลื่อนไหว</div>
              </div>
              {movementJobs.length > 0 && <Chip tone="gold" icon={<Diamond size={5} />}>{movementJobs.length} งาน</Chip>}
            </div>
            {movementJobs.length === 0 ? (
              <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
                <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
                  ยังไม่มีงานที่เคลื่อนไหววันนี้ — จะขึ้นให้เมื่อมีงานที่ท่านติดตามเปลี่ยนสถานะครับ
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {movementJobs.map(job => (
                  <MovementJobCard
                    key={job.project_id}
                    job={job}
                    starred={starred.has(job.project_id)}
                    onStar={() => toggleStar(job.project_id)}
                    detailHref={detailHrefOf(job.project_id)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {tier.id === 'trial' && (
          <div style={{ marginTop: 18 }}>
            <Link href="/portal/packages" style={{ display: 'block' }}>
              <button className="p-btn p-btn-primary" style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center' }}>
                <Icons.Crown size={16} />อัปเกรดเพื่อใช้งานต่อหลังหมดทดลอง
              </button>
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
