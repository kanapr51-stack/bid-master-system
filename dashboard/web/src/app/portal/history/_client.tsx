'use client';

import { useState } from 'react';
import { TopBar, ButlerNote } from '../_ui';
import type { BidderRow, JobBiddersResult, CompetitorProfile, CompetitorProfileResult } from '@/lib/bid-history';

function fmt(n: string | number | null | undefined): string {
  if (n == null || n === '') return '—';
  const num = typeof n === 'string' ? parseFloat(n) : n;
  if (isNaN(num)) return String(n);
  return num.toLocaleString('th-TH');
}

// ── Bidder card ───────────────────────────────────────────────────────────────

function BidderCard({ b, onProfileClick }: { b: BidderRow; onProfileClick: (tin: string) => void }) {
  return (
    <div className="p-card" style={{
      marginBottom: 8,
      borderColor: b.is_winner ? 'var(--accent-deep)' : 'var(--border)',
      background: b.is_winner ? 'var(--gold-glow)' : 'var(--surface)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span style={{ fontWeight: 600, fontSize: 14 }}>{b.bidder_name}</span>
          {b.is_winner && (
            <span className="p-chip" style={{ marginLeft: 8, background: 'var(--accent)', color: '#000', fontSize: 10 }}>ชนะ</span>
          )}
          {b.is_sme && <span className="p-chip" style={{ marginLeft: 4, fontSize: 10 }}>SME</span>}
          {b.is_joint_venture && <span className="p-chip" style={{ marginLeft: 4, fontSize: 10 }}>JV</span>}
        </div>
        {b.bidder_tin && (
          <button
            className="p-btn-outline"
            style={{ fontSize: 11, padding: '2px 8px', flexShrink: 0, marginLeft: 8 }}
            onClick={() => onProfileClick(b.bidder_tin)}
          >
            โปรไฟล์
          </button>
        )}
      </div>
      <div className="p-fg-mute" style={{ fontSize: 11, marginTop: 4 }}>
        TIN: {b.bidder_tin || '—'} · เสนอ {fmt(b.price_proposal)} บาท
        {b.price_agree ? ` · ตกลง ${fmt(b.price_agree)} บาท` : ''}
      </div>
      {b.is_joint_venture && b.jv_partners && (
        <div style={{ fontSize: 11, color: 'var(--accent)', marginTop: 2 }}>JV: {b.jv_partners}</div>
      )}
    </div>
  );
}

// ── Competitor profile ────────────────────────────────────────────────────────

function ProfileView({
  result,
  onBack,
  onJobClick,
}: {
  result: CompetitorProfileResult;
  onBack: () => void;
  onJobClick: (jobId: string) => void;
}) {
  const p = result.profile;
  return (
    <div>
      <button className="p-btn-outline" style={{ marginBottom: 12, fontSize: 12 }} onClick={onBack}>
        ← กลับ
      </button>
      <div className="p-card" style={{ marginBottom: 12, borderColor: 'var(--accent-deep)', background: 'var(--gold-glow)' }}>
        <div className="p-h3" style={{ marginBottom: 2 }}>{p.company_name}</div>
        <div className="p-fg-mute" style={{ fontSize: 11, marginBottom: 10 }}>TIN: {p.bidder_tin}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
          {([
            ['งานทั้งหมด', Number(p.total_bids), ''],
            ['ชนะ', Number(p.total_wins), ''],
            ['อัตราชนะ', Number(p.win_rate_pct), '%'],
            ['Avg Discount', p.avg_discount_pct != null ? Number(p.avg_discount_pct).toFixed(1) : '—', p.avg_discount_pct != null ? '%' : ''],
          ] as [string, string | number, string][]).map(([label, value, unit]) => (
            <div key={label} className="p-card" style={{ textAlign: 'center', padding: '8px 4px' }}>
              <div className="p-fg-mute" style={{ fontSize: 10 }}>{label}</div>
              <div className="p-display" style={{ fontSize: 22 }}>
                {value}<span style={{ fontSize: 12 }}>{unit}</span>
              </div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: 11 }}>
          {p.is_sme && <span className="p-chip" style={{ marginRight: 4 }}>SME</span>}
          {p.has_jv && <span className="p-chip" style={{ marginRight: 4 }}>เคย JV</span>}
        </div>
        {p.provinces?.length > 0 && (
          <div style={{ marginTop: 6, fontSize: 11, color: 'var(--fg-mute)' }}>
            จังหวัด: {p.provinces.join(', ')}
          </div>
        )}
        {p.first_seen && (
          <div style={{ marginTop: 2, fontSize: 11, color: 'var(--fg-mute)' }}>
            พบครั้งแรก: {p.first_seen} · ล่าสุด: {p.last_seen}
          </div>
        )}
      </div>

      <div className="p-label" style={{ marginBottom: 8 }}>20 งานล่าสุด</div>
      {result.recent_jobs.map((j, i) => (
        <div
          key={i}
          className="p-card"
          style={{
            marginBottom: 6,
            cursor: 'pointer',
            borderColor: j.is_winner ? 'var(--accent-deep)' : 'var(--border)',
          }}
          onClick={() => onJobClick(j.job_id)}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <span style={{ fontSize: 13, flex: 1 }}>
              {j.title.length > 65 ? j.title.slice(0, 65) + '…' : j.title}
            </span>
            {j.is_winner && (
              <span className="p-chip" style={{ background: 'var(--accent)', color: '#000', fontSize: 10, marginLeft: 6, flexShrink: 0 }}>ชนะ</span>
            )}
          </div>
          <div className="p-fg-mute" style={{ fontSize: 11, marginTop: 2 }}>
            {j.department} · {j.province} · {j.publish_date} · เสนอ {fmt(j.price_proposal)} บาท
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────────────────

export default function HistoryClient() {
  const [tab, setTab] = useState<'job' | 'company'>('job');
  const [jobId, setJobId] = useState('');
  const [companyQ, setCompanyQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [jobResult, setJobResult] = useState<JobBiddersResult | null>(null);
  const [profileResult, setProfileResult] = useState<CompetitorProfileResult | null>(null);
  const [searchResults, setSearchResults] = useState<CompetitorProfile[]>([]);
  const [error, setError] = useState('');

  function resetState() {
    setError(''); setJobResult(null); setProfileResult(null); setSearchResults([]);
  }

  async function searchJob(id?: string) {
    const q = (id ?? jobId).trim();
    if (!q) return;
    setLoading(true); resetState();
    try {
      const res = await fetch(`/api/portal/history/job/${encodeURIComponent(q)}`);
      if (!res.ok) { setError('ไม่พบข้อมูลงาน ' + q); return; }
      setJobResult(await res.json());
    } catch { setError('เกิดข้อผิดพลาด กรุณาลองใหม่'); }
    finally { setLoading(false); }
  }

  async function searchCompany() {
    const q = companyQ.trim();
    if (!q) return;
    // TIN = all digits — route directly to profile lookup
    if (/^\d{9,13}$/.test(q)) {
      await loadProfile(q);
      return;
    }
    setLoading(true); resetState();
    try {
      const res = await fetch(`/api/portal/history/company?q=${encodeURIComponent(q)}`);
      if (!res.ok) { setError('เกิดข้อผิดพลาด'); return; }
      const data = await res.json();
      setSearchResults(data.results ?? []);
      if (!data.results?.length) setError('ไม่พบบริษัทนี้ในฐานข้อมูล — ระบบมีประวัติจาก 300 งานที่ประมูลแล้วในพื้นที่เป้าหมาย บริษัทที่ไม่เคยเสนอราคาในงานเหล่านั้นจะไม่ปรากฏ');
    } catch { setError('เกิดข้อผิดพลาด กรุณาลองใหม่'); }
    finally { setLoading(false); }
  }

  async function loadProfile(tin: string) {
    setLoading(true); setError(''); setSearchResults([]); setProfileResult(null);
    try {
      const res = await fetch(`/api/portal/history/company?tin=${encodeURIComponent(tin)}`);
      if (!res.ok) { setError('ไม่พบข้อมูลบริษัทนี้'); return; }
      setProfileResult(await res.json());
    } catch { setError('เกิดข้อผิดพลาด'); }
    finally { setLoading(false); }
  }

  function handleJobClick(id: string) {
    setTab('job'); setJobId(id); setProfileResult(null);
    searchJob(id);
  }

  return (
    <div className="p-page">
      <TopBar title="ประวัติการประมูล" subtitle="Bid History" />
      <ButlerNote>ค้นหาว่าใครเคยเสนอราคาในงานนี้ หรือบริษัทนี้เคยชนะงานไหนบ้าง · ฐานข้อมูล 469 บริษัท จาก 300 งานประมูลในพื้นที่นครพนม–บึงกาฬ</ButlerNote>

      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['job', 'company'] as const).map(t => (
          <button
            key={t}
            onClick={() => { setTab(t); resetState(); }}
            style={{
              padding: '6px 14px', fontSize: 13, borderRadius: 6, border: '1px solid var(--border)',
              background: tab === t ? 'var(--accent)' : 'var(--surface)',
              color: tab === t ? '#000' : 'inherit', cursor: 'pointer', fontWeight: tab === t ? 600 : 400,
            }}
          >
            {t === 'job' ? 'ค้นหางาน' : 'ค้นหาบริษัท'}
          </button>
        ))}
      </div>

      {/* Search inputs */}
      {tab === 'job' && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <input
            className="p-input"
            placeholder="Job ID เช่น 6701234567"
            value={jobId}
            onChange={e => setJobId(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && searchJob()}
            style={{ flex: 1 }}
          />
          <button className="p-btn" onClick={() => searchJob()} disabled={loading}>
            {loading ? '…' : 'ค้นหา'}
          </button>
        </div>
      )}

      {tab === 'company' && !profileResult && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <input
            className="p-input"
            placeholder="ชื่อบริษัท หรือ เลขประจำตัวผู้เสียภาษี (TIN)"
            value={companyQ}
            onChange={e => setCompanyQ(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && searchCompany()}
            style={{ flex: 1 }}
          />
          <button className="p-btn" onClick={searchCompany} disabled={loading}>
            {loading ? '…' : 'ค้นหา'}
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="p-card" style={{ color: 'var(--danger, #c00)', marginBottom: 12, fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Job bidders result */}
      {jobResult && (
        <div>
          <div className="p-card" style={{ marginBottom: 12 }}>
            <div className="p-label" style={{ marginBottom: 4 }}>รายละเอียดงาน</div>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{jobResult.job.title}</div>
            <div className="p-fg-mute" style={{ fontSize: 12 }}>
              {jobResult.job.department} · {jobResult.job.province}
              {jobResult.job.budget && ` · งบ ${fmt(jobResult.job.budget)} บาท`}
              {jobResult.job.deadline && ` · ปิด ${jobResult.job.deadline}`}
            </div>
          </div>

          <div className="p-label" style={{ marginBottom: 8 }}>
            ผู้เสนอราคา {jobResult.total} ราย
          </div>

          {jobResult.bidders.map((b, i) => (
            <BidderCard key={i} b={b} onProfileClick={loadProfile} />
          ))}
        </div>
      )}

      {/* Company search results list */}
      {searchResults.length > 0 && !profileResult && (
        <div>
          <div className="p-label" style={{ marginBottom: 8 }}>พบ {searchResults.length} บริษัท</div>
          {searchResults.map((p, i) => (
            <div
              key={i}
              className="p-card"
              style={{ marginBottom: 8, cursor: 'pointer' }}
              onClick={() => loadProfile(p.bidder_tin)}
            >
              <div style={{ fontWeight: 600, fontSize: 14 }}>{p.company_name}</div>
              <div className="p-fg-mute" style={{ fontSize: 11, marginTop: 2 }}>
                TIN: {p.bidder_tin} · {p.total_bids} งาน · ชนะ {p.total_wins} ({Number(p.win_rate_pct)}%)
                {p.is_sme && ' · SME'}
                {p.provinces?.length ? ` · ${p.provinces.slice(0, 2).join(', ')}` : ''}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Full competitor profile */}
      {profileResult && (
        <ProfileView
          result={profileResult}
          onBack={() => setProfileResult(null)}
          onJobClick={handleJobClick}
        />
      )}
    </div>
  );
}
