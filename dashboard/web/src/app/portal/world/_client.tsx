'use client';

import { useState } from 'react';
import Link from 'next/link';
import { type BusinessClass, TIERS } from '@/lib/portal-data';
import type { PortalProfile } from '@/lib/portal-data';
import type { JobGroups, JobStage, TrackedJob, DiscoverGroups, DiscoverJob } from '@/lib/portal-jobs';
import { TopBar, Chip, Icons, Diamond } from '../_ui';
import PushNotifyCard from '@/components/PushNotifyCard';

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

function SumCard({ icon, label, value, unit, accent, href, onClick, active, badge }: { icon: React.ReactNode; label: string; value: number | string; unit: string; accent?: boolean; href?: string; onClick?: () => void; active?: boolean; badge?: string }) {
  const lit = accent || active;
  const content = (
    <div className="p-card" onClick={onClick} style={{ textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 8, padding: 16, borderColor: lit ? 'var(--accent-deep)' : 'var(--border)', background: lit ? 'var(--gold-glow)' : 'var(--surface)', width: '100%', cursor: href || onClick ? 'pointer' : 'default' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: lit ? 'var(--accent)' : 'var(--fg-mute)' }}>
        {icon}
        {href && !accent && <Icons.ChevronRight size={14} />}
        {onClick && (active ? <Icons.Check size={14} /> : <Icons.ChevronRight size={14} />)}
      </div>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div className="p-fg-mute p-mono" style={{ fontSize: 11, letterSpacing: '0.04em', textTransform: 'uppercase' }}>{label}</div>
          {badge && (
            <span className="p-mono" style={{ fontSize: 10, fontWeight: 600, color: 'var(--accent)', background: 'var(--gold-glow)', border: '1px solid var(--accent-deep)', borderRadius: 999, padding: '1px 6px', lineHeight: 1.5 }}>
              {badge}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 4 }}>
          <span className="p-display" style={{ fontSize: typeof value === 'string' ? 22 : 30, color: accent ? 'var(--accent)' : 'inherit', lineHeight: 1 }}>{value}</span>
          <span className="p-fg-dim" style={{ fontSize: 12 }}>{unit}</span>
        </div>
      </div>
    </div>
  );
  if (href) return <Link href={href} style={{ textDecoration: 'none', color: 'inherit' }}>{content}</Link>;
  return content;
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
}

export function WorldClient({ profile, tierId, chatUsed, chatQuota, daysLeft, expiryLabel, classes, subscribedProvinces, jobGroups, discoverGroups, allNotifiedCount, allNotifiedNewToday }: WorldClientProps) {
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

  // กดการ์ด "★ งานที่สนใจ" = กรองบอร์ดเหลือเฉพาะงานติดดาว (กดซ้ำ = เลิกกรอง)
  const [starOnly, setStarOnly] = useState(false);
  const filterOn = starOnly && starred.size > 0;

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
  const totalKeywords = classes.reduce((a, c) => a + c.keywords.length, 0);
  // N+198.1: พื้นที่ครอบคลุม = subscription จริง (แจ้งเตือนตามนี้) union กับที่ตั้งใน classes
  const provincesCount = new Set([...subscribedProvinces, ...classes.flatMap(c => c.geo.provinces)]).size;
  const isUnlimited = chatQuota === -1;
  const quotaPct = isUnlimited ? 100 : Math.round(((chatQuota - chatUsed) / chatQuota) * 100);

  return (
    <div className="p-enter">
      <TopBar
        title="Company World"
        subtitle={profile.companyName}
        right={
          <Link href="/portal/packages" className="p-icon-btn" title="แพ็กเกจ"><Icons.Crown size={18} /></Link>
        }
      />

      <div className="p-page p-page-topbar">
        <PushNotifyCard />

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

        {/* Summary grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {/* N+199: ระบบบริษัทถูกถอด — การ์ดชี้หน้าตั้งค่าแบน */}
          <SumCard icon={<Icons.Map size={16} />} label="พื้นที่ครอบคลุม" value={provincesCount} unit="จังหวัด" href="/portal/settings" />
          {/* N+198.2: ไม่มีคำค้น = เห็นทั้งจังหวัด — โชว์คำแทนเลข 0 (กัญจน์ 2026-07-12) */}
          <SumCard icon={<Icons.Tag size={16} />} label="Keywords" value={totalKeywords > 0 ? totalKeywords : 'ทั้งจังหวัด'} unit={totalKeywords > 0 ? 'คำค้น' : ''} href="/portal/settings" />
          <SumCard icon={<Icons.Bell size={16} />} label="งานที่ติดตาม" value={allJobs.length} unit="งาน" accent />
          {allNotifiedCount > 0 && (
            <SumCard icon={<Icons.Doc size={16} />} label="งานทั้งหมด" value={allNotifiedCount} unit="งาน" href="/portal/jobs"
              badge={allNotifiedNewToday > 0 ? `New+${allNotifiedNewToday}` : undefined} />
          )}
          {starred.size > 0 && (
            <SumCard icon={<span style={{ fontSize: 16 }}>★</span>} label="งานที่สนใจ" value={starred.size} unit="งาน"
              active={filterOn} onClick={() => setStarOnly(v => !v)} />
          )}
        </div>

        {/* Tracked jobs by stage */}
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

        {/* Discovery: งานใหม่ที่แมตช์ */}
        {(() => {
          const discoverAll = [...discover.biddable, ...discover.planning]
            .filter(j => !filterOn || starred.has(j.project_id));
          // N+198: ไม่มี keyword = เห็นทั้งจังหวัด — มีพื้นที่ก็พอ ไม่บังคับคำค้น
          const hasPrefs = provincesCount > 0;
          return (
            <div style={{ marginTop: 26 }}>
              <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 10 }}>
                <div>
                  <div className="p-smallcaps p-fg-mute">งานใหม่ที่แมตช์</div>
                  <div className="p-display" style={{ fontSize: 20, marginTop: 2 }}>✨ Matched For You</div>
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
          );
        })()}

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
