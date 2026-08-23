'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TopBar, Chip, Icons, Diamond } from '../../_ui';
import type { CompanyDetail, CompanyJob, HeadToHead, WonPortfolio } from '@/lib/portal-company-detail';

// ── helpers ─────────────────────────────────────────────────────────────────

function fmtBaht(n: number | null | undefined): string {
  if (!n) return '—';
  return n.toLocaleString('th-TH');
}

// สีกราฟ: hue เดียวกับ token --gold/--emerald แต่ snap เข้า band ที่ผ่าน
// dataviz validator บน surface มืด #1A1714 (lightness/chroma/CVD/contrast PASS ครบ)
const CHART_GOLD = '#B8893A';
const CHART_EMERALD = '#579E6A';

// ── Section header (แพทเทิร์นเดียวกับหน้า job detail) ────────────────────────

function SectionHead({ smallcaps, title, right }: { smallcaps: string; title: string; right?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', margin: '22px 0 10px' }}>
      <div>
        <div className="p-smallcaps p-fg-mute">{smallcaps}</div>
        <div className="p-display" style={{ fontSize: 19, marginTop: 2 }}>{title}</div>
      </div>
      {right}
    </div>
  );
}

// ── Stat cell ────────────────────────────────────────────────────────────────

function Stat({ label, value, unit }: { label: string; value: React.ReactNode; unit?: string }) {
  return (
    <div style={{ flex: 1, minWidth: 0, textAlign: 'center' }}>
      <div className="p-serif" style={{ fontSize: 19, fontWeight: 500 }}>
        {value}{unit && <span className="p-fg-dim" style={{ fontSize: 11 }}> {unit}</span>}
      </div>
      <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em', marginTop: 2 }}>{label}</div>
    </div>
  );
}

// ── Bar row (กราฟแท่งแนวนอน — ป้าย+ค่าเป็น text token, สีอยู่ที่แท่งเท่านั้น) ──

function BarRow({ label, value, max, color, valText }: {
  label: string; value: number; max: number; color: string; valText: string;
}) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
      <span className="p-fg-mute" style={{ width: 64, flexShrink: 0, whiteSpace: 'nowrap' }}>{label}</span>
      <span style={{ flex: 1, background: 'var(--surface-2)', borderRadius: 4, height: 12, overflow: 'hidden' }}>
        <span style={{ display: 'block', height: '100%', width: `${pct}%`, background: color, borderRadius: '0 4px 4px 0' }} />
      </span>
      <span className="p-fg-mute p-mono" style={{ width: 58, flexShrink: 0, textAlign: 'right', fontSize: 11, whiteSpace: 'nowrap' }}>{valText}</span>
    </div>
  );
}

// ── Job row (รายการงาน — ลิงก์เข้าหน้า detail ธีม B) ─────────────────────────

function JobRow({ j, first = false }: { j: CompanyJob; first?: boolean }) {
  const disc = j.discount != null ? `ส่วนลด ${j.discount.toFixed(1)}%` : '—';
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '8px 0', borderTop: first ? 'none' : '1px solid var(--line)' }}>
      <Link href={`/portal/job/${encodeURIComponent(j.project_id)}`} prefetch={false} className="p-fg-accent"
        style={{ textDecoration: 'none', fontSize: 13, lineHeight: 1.45, minWidth: 0 }}>
        {j.is_winner ? '✅ ' : '▫️ '}{j.name}
      </Link>
      <span style={{ textAlign: 'right', flexShrink: 0 }}>
        <span className="p-serif" style={{ fontSize: 13.5, display: 'block' }}>{fmtBaht(j.price)}</span>
        <span className="p-fg-dim" style={{ fontSize: 10.5 }}>{disc}</span>
      </span>
    </div>
  );
}

// ── ⚔️ เทียบกับเรา (head-to-head) ─────────────────────────────────────────────

function H2HSection({ h2h }: { h2h: HeadToHead }) {
  const winPct = h2h.shared ? Math.round((h2h.our_wins / h2h.shared) * 100) : 0;
  const mark = { us: '🟢 เราชนะ', them: '🔴 เขาชนะ', other: '⚪ รายอื่นชนะ' } as const;
  return (
    <div className="p-card">
      <div style={{ display: 'flex', gap: 8 }}>
        <Stat label="เจอกัน" value={h2h.shared} />
        <Stat label="เราชนะ" value={h2h.our_wins} />
        <Stat label="เขาชนะ" value={h2h.their_wins} />
        <Stat label="เราชนะ%" value={`${winPct}%`} />
      </div>
      <div style={{ marginTop: 12 }}>
        {h2h.jobs.slice(0, 10).map((j, i) => (
          <div key={i} style={{ padding: '8px 0', borderTop: '1px solid var(--line)' }}>
            <Link href={`/portal/job/${encodeURIComponent(j.project_id)}`} prefetch={false} className="p-fg-accent"
              style={{ textDecoration: 'none', fontSize: 13, lineHeight: 1.45 }}>
              {j.name}
            </Link>
            <div className="p-fg-mute" style={{ fontSize: 11.5, marginTop: 2 }}>
              {mark[j.winner_side]} · เรา {fmtBaht(j.our_price)} / เขา {fmtBaht(j.their_price)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 🏆 ผลงานที่ชนะ (ทุกวิธีจัดซื้อ) ───────────────────────────────────────────

const PROC_LABELS: Record<string, string> = { all: 'ทั้งหมด', bid: 'ประมูล', specific: 'เจาะจง', other: 'วิธีอื่น' };

function WonSection({ won, hrefOf }: { won: WonPortfolio; hrefOf: (proc: string) => string }) {
  const [open, setOpen] = useState(won.proc !== 'all'); // เปิดเองเมื่อ filter อยู่ (เหมือนหน้า A)
  const g = won.groups;
  const cnt = (key: string) => (key === 'all' ? won.total.count : g[key as 'bid' | 'specific' | 'other'].count);
  return (
    <div className="p-card">
      <div style={{ display: 'flex', gap: 8 }}>
        <Stat label={`ประมูล ${fmtBaht(g.bid.value)}`} value={g.bid.count} />
        <Stat label={`เจาะจง ${fmtBaht(g.specific.value)}`} value={g.specific.count} />
        <Stat label={`รวม ${fmtBaht(won.total.value)}`} value={won.total.count} />
      </div>
      <div className="p-fg-mute" style={{ fontSize: 12, marginTop: 12, display: 'flex', flexDirection: 'column', gap: 4, lineHeight: 1.5 }}>
        {won.top_overall && <span>💎 มูลค่าสูงสุด: {won.top_overall.name} — {fmtBaht(won.top_overall.price)} บาท</span>}
        {won.top_bid && <span>🥇 สูงสุด (ประมูล): {won.top_bid.name} — {fmtBaht(won.top_bid.price)}</span>}
        {won.top_nonbid && <span>🥈 สูงสุด (วิธีอื่น): {won.top_nonbid.name} — {fmtBaht(won.top_nonbid.price)}</span>}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
        {(['all', 'bid', 'specific', 'other'] as const).map(key => (
          <Link key={key} href={hrefOf(key)} style={{ textDecoration: 'none' }}>
            <Chip tone={won.proc === key ? 'gold' : 'outline'}>{PROC_LABELS[key]} {cnt(key)}</Chip>
          </Link>
        ))}
      </div>
      <button className="p-btn p-btn-ghost" onClick={() => setOpen(o => !o)}
        style={{ marginTop: 12, height: 32, padding: '0 12px', fontSize: 12.5, display: 'flex', alignItems: 'center', gap: 5 }}>
        <Icons.ChevronDown size={14} style={{ transform: open ? 'rotate(180deg)' : undefined, transition: 'transform .15s' }} />
        📋 รายชื่องาน ({won.jobs.length})
      </button>
      {open && (
        <div style={{ marginTop: 6 }}>
          {won.jobs.length === 0 && (
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 13, padding: '8px 0' }}>ไม่มีงานในกลุ่มนี้</div>
          )}
          {won.jobs.slice(0, 50).map((j, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, padding: '8px 0', borderTop: '1px solid var(--line)' }}>
              <span style={{ fontSize: 13, lineHeight: 1.45, minWidth: 0 }}>{j.name}</span>
              <span style={{ textAlign: 'right', flexShrink: 0 }}>
                <span className="p-serif" style={{ fontSize: 13.5, display: 'block' }}>{fmtBaht(j.price)}</span>
                <span className="p-fg-dim" style={{ fontSize: 10.5 }}>{j.discount != null ? `ส่วนลด ${j.discount.toFixed(1)}%` : '—'}</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function CompanyDetailClient({ tin, detail, engineDown, from, proc, areaIds, areaLabel }: {
  tin: string;
  detail: CompanyDetail | null;
  engineDown: boolean;
  from: string;
  proc: string;
  areaIds: string;
  areaLabel: string;
}) {
  const router = useRouter();
  const goBack = () => (from ? router.push(`/portal/job/${encodeURIComponent(from)}`) : router.back());

  if (!detail) {
    return (
      <div className="p-enter">
        <TopBar title="ประวัติบริษัท" subtitle={tin} onLeft={goBack} />
        <div className="p-page p-page-topbar">
          <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
              {engineDown ? 'ดึงข้อมูลไม่ได้ชั่วคราว — ลองใหม่อีกครั้งครับ' : 'ไม่พบประวัติบริษัทนี้'}
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

  const p = detail.profile;

  // ลิงก์ chip filter proc — คง from/area_ids/area_label เดิมไว้
  const hrefOf = (nextProc: string) => {
    const qs = new URLSearchParams();
    if (nextProc !== 'all') qs.set('proc', nextProc);
    if (from) qs.set('from', from);
    if (areaIds) qs.set('area_ids', areaIds);
    if (areaLabel) qs.set('area_label', areaLabel);
    const s = qs.toString();
    return `/portal/company/${encodeURIComponent(tin)}${s ? `?${s}` : ''}`;
  };

  const maxBids = Math.max(1, ...p.by_year.map(g => g.bids));
  const maxHist = Math.max(1, ...p.discount_hist.map(x => x.count));

  return (
    <div className="p-enter">
      <TopBar title="ประวัติบริษัท" subtitle={tin} onLeft={goBack} />

      <div className="p-page p-page-topbar">
        {/* หัวบริษัท */}
        <div className="p-gilt">
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.18em' }}>COMPETITOR PROFILE</div>
          <div className="p-display" style={{ fontSize: 21, lineHeight: 1.3, marginTop: 4 }}>
            🏢 {p.name || '(ไม่ระบุชื่อ)'}
          </div>
          {p.is_sme && <div style={{ marginTop: 8 }}><Chip tone="emerald" icon={<Icons.Shield size={11} />}>SME</Chip></div>}
          <div style={{ display: 'flex', gap: 8, marginTop: 14, borderTop: '1px solid var(--line)', paddingTop: 12 }}>
            <Stat label="ยื่น" value={p.total_bids} />
            <Stat label="ชนะ" value={p.wins} />
            <Stat label="win-rate" value={`${Math.round(p.win_rate)}%`} />
            <Stat label="จังหวัด" value={p.provinces.length} />
          </div>
        </div>

        {/* ⚔️ เทียบกับเรา */}
        {detail.h2h && (
          <>
            <SectionHead smallcaps="Head to Head" title={`⚔️ เทียบกับ ${detail.h2h.our_name}`} />
            <H2HSection h2h={detail.h2h} />
          </>
        )}

        {/* 📊 ยื่น–ชนะ รายปี */}
        <SectionHead smallcaps="By Year" title="📊 ยื่น–ชนะ รายปี" />
        <div className="p-card" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {p.by_year.map((g, i) => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <BarRow label={g.year ? `ปี ${g.year}` : 'ไม่ทราบปี'} value={g.bids} max={maxBids} color={CHART_GOLD} valText={`ยื่น ${g.bids}`} />
              <BarRow label="" value={g.wins} max={maxBids} color={CHART_EMERALD} valText={`ชนะ ${g.wins}`} />
            </div>
          ))}
        </div>

        {/* 💸 ส่วนลดที่ชอบเสนอ */}
        <SectionHead smallcaps="Discount Habit" title="💸 ส่วนลดที่ชอบเสนอ"
          right={p.discount_avg != null ? <Chip tone="gold" icon={<Diamond size={5} />}>เฉลี่ย {p.discount_avg.toFixed(1)}%</Chip> : undefined} />
        <div className="p-card" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {p.discount_hist.map((x, i) => (
            <BarRow key={i} label={x.hi != null ? `${x.lo}-${x.hi}%` : `≥${x.lo}%`}
              value={x.count} max={maxHist} color={CHART_GOLD} valText={String(x.count)} />
          ))}
        </div>

        {/* 🏆 ผลงานที่ชนะ */}
        {detail.won && (
          <>
            <SectionHead smallcaps="Won Portfolio" title="🏆 ผลงานที่ชนะ (ทุกวิธีจัดซื้อ)" />
            <WonSection won={detail.won} hrefOf={hrefOf} />
          </>
        )}

        {/* 📍 ผลงานในพื้นที่นี้ (เข้าจากลิงก์ scope) */}
        {detail.area && (
          <>
            <SectionHead smallcaps="This Area" title={`📍 ผลงานในพื้นที่นี้${detail.area_label ? ` — ${detail.area_label}` : ''}`}
              right={<Chip tone="gold" icon={<Diamond size={5} />}>{detail.area.label_count} งาน</Chip>} />
            <div className="p-card">
              {detail.area.jobs.map((j, i) => <JobRow key={i} j={j} first={i === 0} />)}
            </div>
          </>
        )}

        {/* Timeline แยกรายปี */}
        <SectionHead smallcaps="History" title="🗓 ประวัติแยกรายปี" />
        {p.by_year.map((g, i) => (
          <div key={i} style={{ marginBottom: 14 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, margin: '0 0 8px' }}>
              <span className="p-display" style={{ fontSize: 16 }}>{g.year ? `ปี ${g.year}` : 'ไม่ทราบปี'}</span>
              <span className="p-fg-dim" style={{ fontSize: 11.5 }}>ยื่น {g.bids} · ชนะ {g.wins}</span>
            </div>
            <div className="p-card" style={{ paddingTop: 4, paddingBottom: 4 }}>
              {g.jobs.map((j, k) => <JobRow key={k} j={j} first={k === 0} />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
