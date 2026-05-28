'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import { type BusinessClass, type PortalJob, TIERS } from '@/lib/portal-data';
import { TopBar, ButlerNote, Chip, Icons, Crest, Diamond } from '../_ui';
import type { PortalProfile } from '@/lib/portal-data';

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

function SumCard({ icon, label, value, unit, sub, accent, href }: { icon: React.ReactNode; label: string; value: number | string; unit: string; sub?: string; accent?: boolean; href?: string }) {
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
        {sub && <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 4 }}>{sub}</div>}
      </div>
    </div>
  );
  if (href) return <Link href={href} style={{ textDecoration: 'none', color: 'inherit' }}>{content}</Link>;
  return content;
}

// ── Job Card ──────────────────────────────────────────────────────────────────

function JobCard({ job, cls, starred, onStar }: { job: PortalJob; cls?: BusinessClass; starred?: boolean; onStar?: () => void }) {
  const urgency = (job.daysLeft ?? 99) <= 5 ? 'wine' : (job.daysLeft ?? 99) <= 10 ? 'gold' : 'outline';
  return (
    <div className="p-card" style={{ padding: 14, borderColor: starred ? 'var(--accent-deep)' : 'var(--border)', background: starred ? 'var(--gold-glow)' : 'var(--surface)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="p-mono p-fg-mute" style={{ fontSize: 11, letterSpacing: '0.04em', marginBottom: 4 }}>{job.agency}</div>
          <div className="p-display" style={{ fontSize: 15, lineHeight: 1.3 }}>{job.title}</div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
          {onStar && (
            <button onClick={e => { e.stopPropagation(); onStar(); }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: starred ? 'var(--accent)' : 'var(--fg-dim)', fontSize: 18, padding: '0 2px', lineHeight: 1 }}>
              {starred ? '★' : '☆'}
            </button>
          )}
          <Chip tone={urgency} icon={<Icons.Clock size={11} />}>{job.daysLeft} วัน</Chip>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 16, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>งบประมาณ</div>
          <div className="p-serif" style={{ fontSize: 16, fontWeight: 500 }}>
            <span className="p-fg-accent">{job.budget.toLocaleString()}</span>{' '}
            <span className="p-fg-dim" style={{ fontSize: 11 }}>ลบ.</span>
          </div>
        </div>
        {cls && (
          <div style={{ paddingLeft: 16, borderLeft: '1px solid var(--line)' }}>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>ตรงกับ Class</div>
            <div style={{ fontSize: 13, marginTop: 2, color: cls.color }}>{cls.name}</div>
          </div>
        )}
        {job.distance && (
          <div style={{ paddingLeft: 16, borderLeft: '1px solid var(--line)' }}>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>ระยะทาง</div>
            <div className="p-serif" style={{ fontSize: 14 }}>{job.distance} <span className="p-fg-dim" style={{ fontSize: 11 }}>กม.</span></div>
          </div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 12, flexWrap: 'wrap' }}>
        {job.matchedKeywords.slice(0, 3).map(k => <Chip key={k} tone="outline">{k}</Chip>)}
        {job.sme && <Chip tone="emerald">SME +7.5%</Chip>}
        {job.mit && <Chip tone="emerald">MIT</Chip>}
      </div>
    </div>
  );
}

// ── Pre-TOR Card ──────────────────────────────────────────────────────────────

function PhaseDot({ label, active }: { label: string; active?: boolean }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <div style={{ width: 10, height: 10, borderRadius: '50%', background: active ? 'var(--accent)' : 'var(--border)', border: active ? '0' : '1px solid var(--line)' }} />
      <span className="p-mono" style={{ fontSize: 9, letterSpacing: '0.04em', color: active ? 'var(--accent)' : 'var(--fg-dim)' }}>{label}</span>
    </div>
  );
}

function PhaseLine({ active }: { active?: boolean }) {
  return <div style={{ flex: 1, height: 1, marginBottom: 14, background: active ? 'var(--accent-deep)' : 'var(--border)' }} />;
}

function PretorCard({ job, cls }: { job: PortalJob; cls?: BusinessClass }) {
  return (
    <div className="p-card" style={{ padding: 14, position: 'relative', overflow: 'hidden' }}>
      <div style={{ position: 'absolute', top: 0, left: 0, background: 'var(--surface-2)', borderRight: '1px solid var(--accent-deep)', borderBottom: '1px solid var(--accent-deep)', borderBottomRightRadius: 8, padding: '3px 10px', display: 'flex', alignItems: 'center', gap: 6, color: 'var(--accent)' }}>
        <Icons.Doc size={11} />
        <span className="p-mono" style={{ fontSize: 9.5, letterSpacing: '0.12em', fontWeight: 600 }}>PRE-TOR</span>
      </div>
      <div style={{ marginTop: 20 }}>
        <div className="p-mono p-fg-mute" style={{ fontSize: 11, letterSpacing: '0.04em', marginBottom: 4 }}>{job.agency}</div>
        <div className="p-display" style={{ fontSize: 15, lineHeight: 1.3 }}>{job.title}</div>
      </div>
      <div style={{ marginTop: 12 }}>
        <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em', marginBottom: 6 }}>
          ขั้นตอน: <span style={{ color: 'var(--accent)' }}>{job.pretorPhase}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <PhaseDot label="ร่าง" active /><PhaseLine active /><PhaseDot label="รับฟัง" active /><PhaseLine /><PhaseDot label="สรุป" /><PhaseLine /><PhaseDot label="ประมูล" />
        </div>
      </div>
      <div style={{ display: 'flex', gap: 14, marginTop: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>งบประมาณ</div>
          <div className="p-serif" style={{ fontSize: 16, fontWeight: 500 }}><span className="p-fg-accent">{job.budget.toLocaleString()}</span> <span className="p-fg-dim" style={{ fontSize: 11 }}>ลบ.</span></div>
        </div>
        <div style={{ paddingLeft: 14, borderLeft: '1px solid var(--line)' }}>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>ปิดรับความเห็น</div>
          <div className="p-serif" style={{ fontSize: 14 }}>
            <span style={{ color: (job.daysToComment ?? 99) <= 7 ? 'var(--wine-soft)' : 'var(--fg)' }}>{job.daysToComment}</span> <span className="p-fg-dim" style={{ fontSize: 11 }}>วัน</span>
          </div>
        </div>
        <div style={{ paddingLeft: 14, borderLeft: '1px solid var(--line)' }}>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>คาดประมูล</div>
          <div className="p-serif" style={{ fontSize: 13 }}>{job.expectedBidDate}</div>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 12, flexWrap: 'wrap' }}>
        {cls && <Chip tone="outline" icon={<Diamond size={5} color={cls.color} />}>{cls.name}</Chip>}
        {job.matchedKeywords.slice(0, 2).map(k => <Chip key={k} tone="outline">{k}</Chip>)}
        {job.sme && <Chip tone="emerald">SME</Chip>}
      </div>
    </div>
  );
}

// ── Feed Tab ──────────────────────────────────────────────────────────────────

function FeedTab({ active, onClick, label, count, icon }: { active: boolean; onClick: () => void; label: string; count: number; icon: React.ReactNode }) {
  return (
    <button onClick={onClick} style={{ flex: 1, padding: '10px 12px', borderRadius: 8, border: 0, background: active ? 'var(--accent)' : 'transparent', color: active ? 'var(--ink-deep)' : 'var(--fg-mute)', display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', transition: 'background 0.16s', whiteSpace: 'nowrap' }}>
      <span style={{ flexShrink: 0 }}>{icon}</span>
      <span style={{ flex: 1, fontSize: 13, fontWeight: active ? 700 : 600 }}>{label}</span>
      <span className="p-mono" style={{ flexShrink: 0, fontSize: 10, padding: '1px 7px', borderRadius: 999, background: active ? 'rgba(14,13,11,0.20)' : 'var(--line)', fontWeight: 600 }}>{count}</span>
    </button>
  );
}

// ── CompanyMatchesCard ────────────────────────────────────────────────────────

function CompanyMatchesCard({
  cls,
  jobs,
  starred,
  onStar,
}: {
  cls: BusinessClass;
  jobs: PortalJob[];
  starred: Set<string>;
  onStar: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const starredCount = jobs.filter(j => starred.has(j.id)).length;
  const urgentCount = jobs.filter(j => (j.daysLeft ?? 99) <= 5).length;

  return (
    <div className="p-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div
        style={{
          padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 12,
          cursor: 'pointer', borderLeft: `3px solid ${cls.color || 'var(--accent)'}`,
          background: starredCount > 0 ? 'var(--gold-glow)' : 'var(--surface)',
        }}
        onClick={() => setExpanded(v => !v)}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="p-display" style={{ fontSize: 16, lineHeight: 1.2 }}>{cls.companyName || cls.name}</div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10.5, marginTop: 2, letterSpacing: '0.02em' }}>
            {jobs.length} งานที่ตรง{urgentCount > 0 && <span style={{ color: 'var(--wine-soft)' }}> · {urgentCount} เร่งด่วน</span>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
          {starredCount > 0 && (
            <span style={{ color: 'var(--accent)', fontSize: 13 }}>★ {starredCount}</span>
          )}
          <Chip tone={urgentCount > 0 ? 'wine' : 'gold'}>{jobs.length}</Chip>
          <Icons.ChevronDown
            size={14}
            style={{ transform: expanded ? 'none' : 'rotate(-90deg)', transition: 'transform 0.15s', color: 'var(--fg-dim)' }}
          />
        </div>
      </div>

      {expanded && (
        <div style={{ padding: '0 12px 12px', borderTop: '1px solid var(--line)' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 10 }}>
            {jobs.map(job => <JobCard key={job.id} job={job} cls={cls} starred={starred.has(job.id)} onStar={() => onStar(job.id)} />)}
          </div>
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
  jobs: PortalJob[];
  initialStarred?: string[];
}

export function WorldClient({ profile, tierId, chatUsed, chatQuota, daysLeft, expiryLabel, classes, jobs, initialStarred = [] }: WorldClientProps) {
  const [feedTab, setFeedTab] = useState<'bidding' | 'pretor'>('bidding');
  const [starred, setStarred] = useState<Set<string>>(new Set(initialStarred));

  const toggleStar = async (jobId: string) => {
    const next = new Set(starred);
    if (next.has(jobId)) next.delete(jobId); else next.add(jobId);
    setStarred(next);
    try {
      await fetch('/api/portal/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ starred: Array.from(next) }),
      });
    } catch { /* non-critical */ }
  };

  const tier = TIERS.find(t => t.id === tierId) || TIERS[0];
  const biddingJobs = jobs.filter(j => j.stage === 'bidding');
  const pretorJobs = jobs.filter(j => j.stage === 'pretor');
  const recentJobs = feedTab === 'pretor' ? pretorJobs.slice(0, 5) : [];

  // Group bidding jobs by matched class
  const jobsByClass = useMemo(() => {
    const map = new Map<string, PortalJob[]>();
    for (const j of biddingJobs) {
      const key = j.matchedClassId ?? '__unmatched__';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(j);
    }
    return map;
  }, [biddingJobs]);

  const totalKeywords = classes.reduce((a, c) => a + c.keywords.length, 0);
  const provincesSet = useMemo(() => {
    const s = new Set<string>();
    classes.forEach(c => c.geo.provinces.forEach(p => s.add(p)));
    return s;
  }, [classes]);

  const isUnlimited = chatQuota === -1;
  const quotaPct = isUnlimited ? 100 : Math.round(((chatQuota - chatUsed) / chatQuota) * 100);

  return (
    <div className="p-enter">
      <TopBar
        title="Company World"
        subtitle={profile.companyName}
        right={
          <div style={{ display: 'flex', gap: 6 }}>
            <Link href="/portal/packages" className="p-icon-btn" title="แพ็กเกจ"><Icons.Crown size={18} /></Link>
            <button className="p-icon-btn" title="แจ้งเตือน"><Icons.Bell size={18} /></button>
          </div>
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
                {tier.id === 'trial' ? `เหลือ ${daysLeft} วัน · หมดอายุ ${expiryLabel}` : `ต่ออายุอัตโนมัติ · ${expiryLabel}`}
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
                <span style={{ width: `${(daysLeft / 30) * 100}%` }} />
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
          <SumCard icon={<Icons.Map size={16} />} label="พื้นที่ครอบคลุม" value={provincesSet.size} unit="จังหวัด" href="/portal/classes" />
          <SumCard icon={<Icons.Tag size={16} />} label="Keywords" value={totalKeywords} unit="คำค้น" href="/portal/classes" />
          <SumCard icon={<Icons.Bell size={16} />} label="งานวันนี้" value={jobs.length} unit="ที่ตรงเงื่อนไข" accent />
          {starred.size > 0 && (
            <SumCard icon={<span style={{ fontSize: 16 }}>★</span>} label="งานที่สนใจ" value={starred.size} unit="งาน" />
          )}
        </div>

        {/* Recent matches */}
        <div style={{ marginTop: 22, marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 10 }}>
            <div>
              <div className="p-smallcaps p-fg-mute">งานที่ Sebastian พบล่าสุด</div>
              <div className="p-display" style={{ fontSize: 20, marginTop: 2 }}>Recent Matches</div>
            </div>
            <Chip tone="gold" icon={<Diamond size={5} />}>{jobs.length} วันนี้</Chip>
          </div>
          <div style={{ display: 'flex', gap: 4, padding: 4, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10 }}>
            <FeedTab active={feedTab === 'bidding'} onClick={() => setFeedTab('bidding')} label="กำลังประมูล" count={biddingJobs.length} icon={<Icons.Bell size={12} />} />
            <FeedTab active={feedTab === 'pretor'} onClick={() => setFeedTab('pretor')} label="Pre-TOR" count={pretorJobs.length} icon={<Icons.Doc size={12} />} />
          </div>
        </div>

        {/* งานที่สนใจ */}
        {starred.size > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ color: 'var(--accent)', fontSize: 16 }}>★</span>
              <div className="p-label" style={{ margin: 0 }}>งานที่สนใจ ({starred.size})</div>
            </div>
            {jobs.filter(j => starred.has(j.id)).map(job => (
              <JobCard key={job.id} job={job}
                cls={classes.find(c => c.id === job.matchedClassId)}
                starred={true} onStar={() => toggleStar(job.id)} />
            ))}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {feedTab === 'bidding' ? (
            biddingJobs.length === 0 ? (
              <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
                <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>ยังไม่พบงานในประเภทนี้ ผมจะแจ้งให้ทราบทันทีที่พบครับท่าน</div>
              </div>
            ) : (
              <>
                {/* Company grouped cards — collapsed by default */}
                {classes.map(cls => {
                  const clsJobs = jobsByClass.get(cls.id) ?? [];
                  if (clsJobs.length === 0) return null;
                  return <CompanyMatchesCard key={cls.id} cls={cls} jobs={clsJobs} starred={starred} onStar={toggleStar} />;
                })}
                {/* Unmatched jobs (no class) */}
                {(jobsByClass.get('__unmatched__') ?? []).map(job => (
                  <JobCard key={job.id} job={job} starred={starred.has(job.id)} onStar={() => toggleStar(job.id)} />
                ))}
              </>
            )
          ) : (
            recentJobs.length === 0 ? (
              <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
                <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>ยังไม่พบงานในประเภทนี้ ผมจะแจ้งให้ทราบทันทีที่พบครับท่าน</div>
              </div>
            ) : (
              recentJobs.map(job => <PretorCard key={job.id} job={job} cls={classes.find(c => c.id === job.matchedClassId)} />)
            )
          )}
        </div>

        {/* Butler note */}
        <div style={{ marginTop: 18 }}>
          <ButlerNote tone="gold">
            {feedTab === 'bidding' ? (
              <>ท่านครับ — วันนี้ผมพบงานที่กำลังประมูล <span className="p-mono" style={{ fontSize: 13 }}>{biddingJobs.length}</span> งาน
              {biddingJobs.length > 0 && <> งานที่ปิดเร็วที่สุดเหลือ <span className="p-mono p-fg-accent" style={{ fontSize: 13, fontStyle: 'normal' }}>{Math.min(...biddingJobs.map(j => j.daysLeft ?? 99))} วัน</span> ขอแนะนำให้ดูก่อนนะครับ</>}</>
            ) : (
              <>นอกจากงานประมูลแล้ว ผมยังพบ <span className="p-mono" style={{ fontStyle: 'normal', fontSize: 13 }}>Pre-TOR {pretorJobs.length} ร่าง</span> — ท่านสามารถส่งความเห็นได้ก่อนประกาศจริง เพื่อเตรียมตัวล่วงหน้าครับ</>
            )}
          </ButlerNote>
        </div>

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
