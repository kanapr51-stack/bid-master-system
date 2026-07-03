'use client';

import { useState } from 'react';
import Link from 'next/link';
import { type BusinessClass, TIERS } from '@/lib/portal-data';
import type { PortalProfile } from '@/lib/portal-data';
import type { JobGroups, JobStage, TrackedJob, DiscoverGroups, DiscoverJob } from '@/lib/portal-jobs';
import { TopBar, Chip, Icons, Diamond } from '../_ui';

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

function SumCard({ icon, label, value, unit, accent, href }: { icon: React.ReactNode; label: string; value: number | string; unit: string; accent?: boolean; href?: string }) {
  const content = (
    <div className="p-card" style={{ textAlign: 'left', display: 'flex', flexDirection: 'column', gap: 8, padding: 16, borderColor: accent ? 'var(--accent-deep)' : 'var(--border)', background: accent ? 'var(--gold-glow)' : 'var(--surface)', width: '100%', cursor: href ? 'pointer' : 'default' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: accent ? 'var(--accent)' : 'var(--fg-mute)' }}>
        {icon}
        {href && !accent && <Icons.ChevronRight size={14} />}
      </div>
      <div>
        <div className="p-fg-mute p-mono" style={{ fontSize: 11, letterSpacing: '0.04em', textTransform: 'uppercase' }}>{label}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 4 }}>
          <span className="p-display" style={{ fontSize: 30, color: accent ? 'var(--accent)' : 'inherit', lineHeight: 1 }}>{value}</span>
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
  { key: 'pre', label: 'ระยะวางแผน', icon: '⚪' },
  { key: 'cancelled', label: 'ยกเลิก', icon: '❌' },
];

// ── Tracked Job Card ──────────────────────────────────────────────────────────

function TrackedJobCard({ job, stage, starred, onStar }: { job: TrackedJob; stage: JobStage; starred: boolean; onStar: () => void }) {
  const dl = daysLeftOf(job.deadline);
  const urgency = dl === null ? 'outline' : dl <= 5 ? 'wine' : dl <= 10 ? 'gold' : 'outline';
  return (
    <div className="p-card" style={{ padding: 14, borderColor: starred ? 'var(--accent-deep)' : 'var(--border)', background: starred ? 'var(--gold-glow)' : 'var(--surface)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          {job.location && <div className="p-mono p-fg-mute" style={{ fontSize: 11, letterSpacing: '0.04em', marginBottom: 4 }}>{job.location}</div>}
          <div className="p-display" style={{ fontSize: 15, lineHeight: 1.3 }}>{job.name}</div>
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
    </div>
  );
}

// ── Discover Card ─────────────────────────────────────────────────────────────

function DiscoverCard({ job, following, onFollow, starred, onStar }: {
  job: DiscoverJob; following: boolean; onFollow: () => void; starred: boolean; onStar: () => void;
}) {
  const dl = daysLeftOf(job.deadline);
  const urgency = dl === null ? 'outline' : dl <= 5 ? 'wine' : dl <= 10 ? 'gold' : 'outline';
  return (
    <div className="p-card" style={{ padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          {job.location && <div className="p-mono p-fg-mute" style={{ fontSize: 11, letterSpacing: '0.04em', marginBottom: 4 }}>{job.location}</div>}
          <div className="p-display" style={{ fontSize: 15, lineHeight: 1.3 }}>{job.name}</div>
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
  jobGroups: JobGroups;
  discoverGroups: DiscoverGroups;
}

export function WorldClient({ profile, tierId, chatUsed, chatQuota, daysLeft, expiryLabel, classes, jobGroups, discoverGroups }: WorldClientProps) {
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
  const provincesCount = new Set(classes.flatMap(c => c.geo.provinces)).size;
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
        {/* Tier banner */}
        <div className="p-gilt" style={{ marginBottom: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="p-mono" style={{ fontSize: 10, letterSpacing: '0.18em', color: 'var(--accent)' }}>CURRENT TIER · {tier.name.toUpperCase()}</div>
              <div className="p-display" style={{ fontSize: 22, marginTop: 4 }}>{tier.id === 'trial' ? 'ทดลองใช้งาน' : tier.nameTh}</div>
              <div className="p-fg-mute" style={{ fontSize: 12.5, marginTop: 2 }}>
                {tier.id === 'trial'
                  ? `เหลือ ${daysLeft} วัน · หมดอายุ ${expiryLabel}`
                  : expiryLabel ? `ใช้ได้ถึง ${expiryLabel}` : 'ติดต่อแอดมินเรื่องรอบบิล'}
              </div>
            </div>
            <Link href="/portal/packages">
              <button className="p-btn p-btn-primary" style={{ height: 36, padding: '0 14px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Icons.Crown size={14} />{tier.id === 'trial' ? 'อัปเกรด' : 'เปลี่ยน'}
              </button>
            </Link>
          </div>
          {tier.id === 'trial' && (
            <>
              <div className="p-deadline-bar" style={{ marginTop: 14 }}>
                <span style={{ width: `${Math.min(100, (daysLeft / 30) * 100)}%` }} />
              </div>
              <div className="p-mono p-fg-dim" style={{ fontSize: 10, marginTop: 6, letterSpacing: '0.06em', display: 'flex', justifyContent: 'space-between' }}>
                <span>0 / 30 วัน</span><span>เหลือ {daysLeft}</span>
              </div>
            </>
          )}
        </div>

        {/* Sebastian quota */}
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

        {/* Summary grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <SumCard icon={<Icons.Layers size={16} />} label="บริษัทของฉัน" value={classes.length} unit="บริษัท" href="/portal/classes" />
          <SumCard icon={<Icons.Map size={16} />} label="พื้นที่ครอบคลุม" value={provincesCount} unit="จังหวัด" href="/portal/classes" />
          <SumCard icon={<Icons.Tag size={16} />} label="Keywords" value={totalKeywords} unit="คำค้น" href="/portal/classes" />
          <SumCard icon={<Icons.Bell size={16} />} label="งานที่ติดตาม" value={allJobs.length} unit="งาน" accent />
          {starred.size > 0 && (
            <SumCard icon={<span style={{ fontSize: 16 }}>★</span>} label="งานที่สนใจ" value={starred.size} unit="งาน" />
          )}
        </div>

        {/* Tracked jobs by stage */}
        <div style={{ marginTop: 22 }}>
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 10 }}>
            <div>
              <div className="p-smallcaps p-fg-mute">งานที่ท่านติดตาม</div>
              <div className="p-display" style={{ fontSize: 20, marginTop: 2 }}>Tracked Bids</div>
            </div>
            <Chip tone="gold" icon={<Diamond size={5} />}>{allJobs.length} งาน</Chip>
          </div>

          {allJobs.length === 0 ? (
            <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
              <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
                ยังไม่มีงานที่ติดตาม — ระบบจะเพิ่มให้เมื่อเจองานตรงพื้นที่/หมวดของท่านครับ
              </div>
            </div>
          ) : (
            STAGE_META.map(({ key, label, icon }) => {
              const jobs = jobGroups[key];
              if (!jobs || jobs.length === 0) return null;
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
          const discoverAll = [...discover.biddable, ...discover.planning];
          const hasPrefs = provincesCount > 0 && totalKeywords > 0;
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
                    ตั้งค่าพื้นที่และคำค้นในหน้า &quot;บริษัทของฉัน&quot; เพื่อให้ระบบหางานที่ตรงให้ท่านครับ
                  </div>
                  <Link href="/portal/classes"><button className="p-btn p-btn-primary" style={{ marginTop: 12, height: 34, padding: '0 16px', fontSize: 13 }}>ไปตั้งค่า</button></Link>
                </div>
              ) : discoverAll.length === 0 ? (
                <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
                  <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
                    ยังไม่มีงานใหม่ที่ตรงเกณฑ์วันนี้ — ระบบจะอัปเดตให้เมื่อมีงานเข้าครับ
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
