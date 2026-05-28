'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { TopBar, Chip, Icons, ButlerNote, Diamond } from '../_ui';
import type { BusinessClass } from '@/lib/portal-data';
import type { CompetitorProfileResult } from '@/lib/bid-history';

// ── StatCard ──────────────────────────────────────────────────────────────────

function StatCard({ label, value, unit, valueColor }: { label: string; value: string | number; unit?: string; valueColor?: string }) {
  return (
    <div style={{
      padding: '14px 12px', background: 'var(--surface)',
      border: '1px solid var(--accent-deep)', borderRadius: 10, textAlign: 'center',
    }}>
      <div className="p-mono p-fg-mute" style={{ fontSize: 10.5, letterSpacing: '0.04em', marginBottom: 6 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: 3 }}>
        <span className="p-display" style={{ fontSize: typeof value === 'string' && value.length > 4 ? 18 : 24, color: valueColor || 'var(--fg)', lineHeight: 1 }}>{value}</span>
        {unit && <span className="p-fg-dim" style={{ fontSize: 11 }}>{unit}</span>}
      </div>
    </div>
  );
}

// ── ParticipationRow ──────────────────────────────────────────────────────────

function ParticipationRow({ j, discPct }: {
  j: { job_id: string; title: string; province: string; publish_date: string; price_proposal: string; is_winner: boolean; budget?: string };
  discPct: number | null;
}) {
  return (
    <div className="p-card" style={{
      padding: 14,
      border: `1px solid ${j.is_winner ? 'var(--accent-deep)' : 'var(--border)'}`,
      background: j.is_winner ? 'var(--gold-glow)' : 'var(--surface)',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
        <div className="p-display" style={{ fontSize: 14.5, lineHeight: 1.35, flex: 1 }}>
          {j.title.length > 70 ? j.title.slice(0, 70) + '…' : j.title}
        </div>
        {j.is_winner && (
          <span style={{
            padding: '2px 9px', borderRadius: 999,
            background: 'var(--accent)', color: 'var(--ink-deep)',
            fontSize: 10.5, fontWeight: 700, letterSpacing: '0.04em',
            fontFamily: 'var(--font-mono)', flexShrink: 0,
          }}>ชนะ</span>
        )}
      </div>
      <div className="p-mono p-fg-dim" style={{ fontSize: 10.5, marginTop: 6, letterSpacing: '0.02em', lineHeight: 1.55 }}>
        {j.province} · {j.publish_date} · เสนอ{' '}
        <span style={{ color: 'var(--fg)' }}>{parseFloat(j.price_proposal).toLocaleString()}</span> บาท
        {discPct != null && (
          <span style={{ color: 'var(--accent)' }}> · ลด {discPct.toFixed(1)}% จากงบ</span>
        )}
      </div>
    </div>
  );
}

// ── CoverageCard ──────────────────────────────────────────────────────────────

function CoverageCard({ cls, onEdit }: { cls: BusinessClass; onEdit: () => void }) {
  const provinces = cls.geo?.provinces?.length || 0;
  const districts = cls.geo?.districts?.length || 0;
  const tambons = cls.geo?.tambons?.length || 0;
  const hasRadius = (cls.geo?.radiusKm || 0) > 0 && cls.geo?.gps;
  const keywords = (cls.keywords || []).length;
  const budgetMin = cls.budgetMinBaht ?? 1_000_000;
  const budgetMax = cls.budgetMaxBaht ?? 50_000_000;

  return (
    <div className="p-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: 14, borderLeft: `3px solid ${cls.color || 'var(--accent)'}` }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
          {[['จังหวัด', provinces], ['อำเภอ', districts], ['ตำบล', tambons]].map(([l, v]) => (
            <div key={l as string} style={{ padding: '10px 8px', borderRadius: 8, background: 'var(--surface-2)', border: '1px solid var(--line)', textAlign: 'center' }}>
              <div className="p-display" style={{ fontSize: 20, color: 'var(--accent)', lineHeight: 1 }}>{v}</div>
              <div className="p-mono p-fg-dim" style={{ fontSize: 9.5, letterSpacing: '0.06em', marginTop: 4, textTransform: 'uppercase' }}>{l}</div>
            </div>
          ))}
        </div>

        {hasRadius && cls.geo?.gps && (
          <div style={{ marginTop: 12, padding: '10px 12px', borderRadius: 8, background: 'var(--surface-2)', border: '1px solid var(--line)', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ color: 'var(--accent)' }}><Icons.Compass size={16} /></div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5 }}>{cls.geo.gps.label || 'โรงงาน'}</div>
              <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.04em' }}>รัศมี {cls.geo.radiusKm} กม.</div>
            </div>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 12 }}>
          <div>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em', marginBottom: 4 }}>KEYWORDS</div>
            <div className="p-display p-fg-accent" style={{ fontSize: 18 }}>{keywords} <span className="p-fg-dim" style={{ fontSize: 11 }}>คำ</span></div>
          </div>
          <div>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em', marginBottom: 4 }}>งบที่รับ</div>
            <div className="p-serif" style={{ fontSize: 13, lineHeight: 1.3 }}>
              {(budgetMin / 1_000_000).toLocaleString()} – {(budgetMax / 1_000_000).toLocaleString()}
              <span className="p-fg-dim" style={{ fontSize: 11 }}> ลบ.</span>
            </div>
          </div>
        </div>

        <button
          className="p-btn p-btn-ghost"
          onClick={onEdit}
          style={{ width: '100%', marginTop: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
        >
          <Icons.Edit size={14} />แก้ไขตั้งค่าใน &quot;บริษัท&quot;
        </button>
      </div>
    </div>
  );
}

// ── CompanyStatsClient ────────────────────────────────────────────────────────

interface Props {
  cls: BusinessClass | null;
  allClasses: BusinessClass[];
}

export function CompanyStatsClient({ cls, allClasses }: Props) {
  const router = useRouter();
  const [searchQ, setSearchQ] = useState(cls?.companyName || cls?.name || '');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CompetitorProfileResult | null>(null);
  const [error, setError] = useState('');

  const fetchStats = async (q: string) => {
    if (!q.trim()) return;
    setLoading(true); setError(''); setResult(null);
    try {
      const endpoint = /^\d{9,13}$/.test(q.trim())
        ? `/api/portal/history/company?tin=${encodeURIComponent(q.trim())}`
        : `/api/portal/history/company?q=${encodeURIComponent(q.trim())}`;
      const res = await fetch(endpoint);
      if (!res.ok) { setError('ไม่พบข้อมูลบริษัทในฐานข้อมูล'); return; }
      const data = await res.json();
      if (data.profile) {
        setResult(data as CompetitorProfileResult);
      } else if (data.results?.length > 0) {
        const tin = data.results[0].bidder_tin;
        const res2 = await fetch(`/api/portal/history/company?tin=${encodeURIComponent(tin)}`);
        if (res2.ok) setResult(await res2.json());
        else setError('ไม่พบข้อมูลโดยละเอียด');
      } else {
        setError('ไม่พบบริษัทนี้ในฐานข้อมูล — ลองค้นด้วยชื่อเต็มหรือเลขประจำตัวผู้เสียภาษี');
      }
    } catch { setError('เกิดข้อผิดพลาด กรุณาลองใหม่'); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (searchQ) fetchStats(searchQ);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!cls) {
    return (
      <div className="p-enter">
        <TopBar title="สถิติบริษัท" subtitle="Company Stats" onLeft={() => router.push('/portal/profile')} />
        <div className="p-page p-page-topbar">
          <div className="p-card" style={{ textAlign: 'center', padding: 24 }}>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>ไม่พบบริษัทที่ระบุครับท่าน</div>
          </div>
          {allClasses.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 10 }}>บริษัทของท่าน</div>
              {allClasses.map(c => (
                <button key={c.id} className="p-card"
                  style={{ width: '100%', textAlign: 'left', padding: 14, marginBottom: 8, cursor: 'pointer', display: 'block', borderLeft: `3px solid ${c.color || 'var(--accent)'}` }}
                  onClick={() => router.push(`/portal/company-stats?classId=${c.id}`)}>
                  <div className="p-display" style={{ fontSize: 16 }}>{c.companyName || c.name}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  const p = result?.profile;
  const reliabilityColor = p
    ? Number(p.total_bids) >= 20 ? 'var(--emerald)' : Number(p.total_bids) >= 10 ? 'var(--accent)' : Number(p.total_bids) >= 3 ? 'var(--wine-soft)' : 'var(--fg-mute)'
    : 'var(--fg-mute)';
  const reliabilityLabel = p
    ? Number(p.total_bids) >= 20 ? 'สูง' : Number(p.total_bids) >= 10 ? 'ปานกลาง' : Number(p.total_bids) >= 3 ? 'ต่ำ' : 'น้อยมาก'
    : '—';

  return (
    <div className="p-enter">
      <TopBar
        title={cls.companyName || cls.name}
        subtitle="Company Stats · สถิติบริษัท"
        onLeft={() => router.push('/portal/profile')}
      />

      <div className="p-page p-page-topbar">
        {/* Identity card */}
        <div className="p-gilt" style={{ marginBottom: 14 }}>
          <div className="p-mono" style={{ fontSize: 10, letterSpacing: '0.18em', color: 'var(--accent)' }}>COMPANY · บริษัทของท่าน</div>
          <div className="p-display" style={{ fontSize: 22, lineHeight: 1.3, marginTop: 4 }}>{cls.companyName || cls.name}</div>
          {p && (
            <div className="p-mono p-fg-dim" style={{ fontSize: 11.5, marginTop: 6, letterSpacing: '0.02em' }}>TIN: {p.bidder_tin}</div>
          )}
          <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
            {(cls.businessTypes || []).map(t => (
              <Chip key={t} tone="outline" icon={<Diamond size={5} color={cls.color} />}>{t}</Chip>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
            {cls.isSME && <Chip tone="emerald" icon={<Icons.Shield size={11} />}>SME +7.5%</Chip>}
            {cls.isMIT && <Chip tone="emerald" icon={<Icons.Flag size={11} />}>MIT</Chip>}
          </div>
        </div>

        {/* Search to link to bid history */}
        <div style={{ marginBottom: 16 }}>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 8 }}>ค้นหาประวัติประมูล</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              className="p-input"
              value={searchQ}
              onChange={e => setSearchQ(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && fetchStats(searchQ)}
              placeholder="ชื่อบริษัท หรือ เลขประจำตัวผู้เสียภาษี"
              style={{ flex: 1 }}
            />
            <button className="p-btn p-btn-primary" onClick={() => fetchStats(searchQ)} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {loading ? '…' : <><Icons.Search size={14} />ค้นหา</>}
            </button>
          </div>
          {error && <div style={{ color: 'var(--wine-soft)', fontSize: 12, marginTop: 6 }}>{error}</div>}
        </div>

        {/* Stats panel */}
        {p && (
          <>
            <div style={{ marginBottom: 6 }}>
              <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 4 }}>BID PERFORMANCE</div>
              <div className="p-display" style={{ fontSize: 18, marginTop: 2 }}>สถิติประมูลปัจจุบัน</div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
              <StatCard label="งานทั้งหมด" value={p.total_bids} />
              <StatCard label="ชนะ" value={p.total_wins} />
              <StatCard label="อัตราชนะ" value={Number(p.win_rate_pct).toFixed(1)} unit="%" />
              <StatCard label="ลดจากงบ (เฉลี่ย)" value={p.avg_discount_from_budget_pct != null ? Number(p.avg_discount_from_budget_pct).toFixed(1) : '—'} unit={p.avg_discount_from_budget_pct != null ? '%' : ''} />
              <StatCard label="ส่วนเบี่ยงเบน (σ)" value={p.stddev_discount_pct != null ? Number(p.stddev_discount_pct).toFixed(1) : '—'} unit={p.stddev_discount_pct != null ? '%' : ''} />
              <StatCard label="ความน่าเชื่อถือ" value={reliabilityLabel} unit={`(${p.total_bids} งาน)`} valueColor={reliabilityColor} />
            </div>

            {p.first_seen && (
              <div className="p-mono p-fg-dim" style={{ fontSize: 11, marginBottom: 16, lineHeight: 1.6, letterSpacing: '0.02em' }}>
                พบครั้งแรก: {p.first_seen} · ล่าสุด: {p.last_seen}
              </div>
            )}
          </>
        )}

        {/* Job history */}
        {result && result.recent_jobs.length > 0 && (
          <div style={{ marginBottom: 22 }}>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 4 }}>BID HISTORY</div>
            <div className="p-display" style={{ fontSize: 18, marginTop: 2, marginBottom: 10 }}>ประวัติทั้งหมด · {result.recent_jobs.length} งาน</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {result.recent_jobs.map((j, i) => {
                const b = j.budget ? parseFloat(j.budget.replace(/,/g, '')) : null;
                const pp = j.price_proposal ? parseFloat(j.price_proposal) : null;
                const discPct = b && pp && b > 0 ? (b - pp) / b * 100 : null;
                return <ParticipationRow key={i} j={j} discPct={discPct} />;
              })}
            </div>
          </div>
        )}

        {/* Coverage */}
        <div style={{ marginBottom: 22 }}>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 4 }}>CONFIGURED COVERAGE</div>
          <div className="p-display" style={{ fontSize: 18, marginTop: 2, marginBottom: 10 }}>ขอบเขตที่ตั้งไว้</div>
          <CoverageCard cls={cls} onEdit={() => router.push('/portal/classes')} />
        </div>

        {/* Future analytics */}
        <div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 4 }}>COMING SOON · สถิติเชิงลึก</div>
          <div className="p-display" style={{ fontSize: 18, marginTop: 2, marginBottom: 10 }}>กำลังพัฒนา</div>
          <div className="p-card" style={{ padding: 0, overflow: 'hidden' }}>
            {[
              { icon: <Icons.TrendUp size={16} />, label: 'แนวโน้มการประมูลรายไตรมาส', hint: 'เปรียบเทียบจำนวนงาน · งบประมาณ · อัตราชนะ' },
              { icon: <Icons.Compass size={16} />, label: 'Heatmap งานที่ชนะ', hint: 'กระจายตามจังหวัด/อำเภอ — เห็นจุดแข็งเชิงพื้นที่' },
              { icon: <Icons.Layers size={16} />, label: 'วิเคราะห์คู่แข่งตัวต่อตัว', hint: 'Head-to-head — บริษัทไหนพบกันบ่อย ใครชนะมากกว่า' },
              { icon: <Icons.Doc size={16} />, label: 'คุณภาพข้อเสนอ', hint: 'เทียบเสนอราคา vs ราคากลาง · เวลายื่นเอกสาร' },
              { icon: <Icons.Coin size={16} />, label: 'Cash Flow Forecast', hint: 'ประมาณการรายรับจากงานที่กำลังประมูล' },
            ].map((it, i) => (
              <div key={i} style={{
                padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 12,
                borderTop: i > 0 ? '1px solid var(--line)' : 0, opacity: 0.85,
              }}>
                <div style={{ color: 'var(--fg-mute)', flexShrink: 0 }}>{it.icon}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{it.label}</div>
                  <div className="p-fg-dim" style={{ fontSize: 11.5, marginTop: 2, lineHeight: 1.4 }}>{it.hint}</div>
                </div>
                <span className="p-chip p-chip-outline" style={{ fontSize: 9.5, flexShrink: 0 }}>เร็วๆ นี้</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ marginTop: 22 }}>
          <ButlerNote tone="gold">
            Sebastian กำลังพัฒนา Analytics เชิงลึกสำหรับบริษัทของท่านครับ — ข้อมูลที่ท่านเห็นนี้มาจากประวัติการประมูลจริงในฐานข้อมูล
          </ButlerNote>
        </div>
      </div>
    </div>
  );
}
