'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { TopBar, Chip, Icons, Diamond } from '../../_ui';
import type { JobDetail, JobNote, CustomCalc, CompanyTable } from '@/lib/portal-job-detail';

// ── helpers ─────────────────────────────────────────────────────────────────

function fmtBaht(n: number | null | undefined): string {
  if (!n) return '—';
  return n.toLocaleString('th-TH');
}

function daysLeftOf(deadline: string | null): number | null {
  if (!deadline) return null;
  const d = new Date(deadline);
  if (isNaN(d.getTime())) return null;
  return Math.max(0, Math.ceil((d.getTime() - Date.now()) / 86400000));
}

// ตัด prefix นิติบุคคล — mirror portal_views._norm_name (dedupe checkbox คู่แข่ง)
const LEGAL_TOKENS = ['ห้างหุ้นส่วนจำกัด', 'ห้างหุ้นส่วนสามัญ', 'หจก.', 'หจก', 'บริษัท',
  'บจก.', 'บจก', 'จำกัด', '(มหาชน)', 'มหาชน', 'นางสาว', 'นาง', 'นาย', 'กิจการร่วมค้า'];

function normName(s: string): string {
  let out = s || '';
  for (const tok of LEGAL_TOKENS) out = out.split(tok).join('');
  return out.replace(/[\s.]/g, '');
}

// ── Section header ───────────────────────────────────────────────────────────

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

// ── Company tables (คู่แข่งต่อ scope) ─────────────────────────────────────────

function CompanyTables({ tables }: { tables: CompanyTable[] }) {
  return (
    <>
      {tables.filter(t => t.companies?.length).map((blk, bi) => (
        <div key={bi} className="p-card" style={{ padding: 0, overflow: 'hidden', marginBottom: 10 }}>
          <div style={{ padding: '12px 14px 10px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span className="p-display" style={{ fontSize: 15 }}>🏢 คู่แข่ง{blk.label}</span>
            <Chip tone="outline">{blk.n} งาน {blk.conf_tag}</Chip>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="p-table">
              <thead>
                <tr><th style={{ textAlign: 'left' }}>บริษัท</th><th>งาน</th><th>ลด%</th></tr>
              </thead>
              <tbody>
                {blk.companies.map((c, i) => (
                  <tr key={i}>
                    <td style={{ textAlign: 'left' }}>
                      {c.href
                        ? <a href={c.href} className="p-fg-accent" style={{ textDecoration: 'none' }}>{c.name}</a>
                        : <span className="p-fg-mute">{c.name}</span>}
                    </td>
                    <td>{c.games}</td>
                    <td>{c.median != null ? `${Math.round(c.median)}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </>
  );
}

// ── Winrate table (โอกาสชนะตามจำนวนผู้ยื่น) ───────────────────────────────────

function WinrateSection({ wt }: { wt: NonNullable<JobDetail['winrate_table']> }) {
  return (
    <div className="p-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ overflowX: 'auto' }}>
        <table className="p-table">
          <thead>
            <tr>
              <th style={{ textAlign: 'left' }}>ราคายื่น</th>
              {wt.ns.map(k => <th key={k}>{k} ราย</th>)}
            </tr>
          </thead>
          <tbody>
            {wt.rows.map(([price, ws], i) => (
              <tr key={i}>
                <td className="p-mono" style={{ textAlign: 'left', whiteSpace: 'nowrap' }}>{fmtBaht(price)}</td>
                {ws.map((w, j) => <td key={j}>{w}%</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="p-fg-dim" style={{ fontSize: 11.5, padding: '10px 14px', lineHeight: 1.6 }}>
        📊 สนามนี้เฉลี่ย {Math.round(wt.n_mean)} ผู้ยื่น{wt.ns.length > 1 ? ` (±${Math.round(wt.n_sd)})` : ''} · จาก {wt.n_auctions} งาน · {wt.n_bids} ราย
        {wt.conf && <><br />{wt.conf[0]} โอกาส% อิง{wt.conf[1]} (พื้นที่นี้ข้อมูลบาง)</>}
      </div>
    </div>
  );
}

// ── ML band (แถบส่วนลดจากสถิติ LightGBM — โชว์ได้แม้ไม่มีตารางคู่แข่ง) ─────────

function MlBandCard({ band }: { band: NonNullable<JobDetail['ml_band']> }) {
  return (
    <div className="p-card" style={{ padding: '12px 14px' }}>
      <div style={{ fontSize: 13, lineHeight: 1.7 }}>
        📈 <span className="p-fg-mute">สถิติงานลักษณะเดียวกันในพื้นที่:</span>{' '}
        ยื่นลด ≥{band.disc_p80}% <span className="p-mono">(≈{fmtBaht(band.price_p80)} บ.)</span>
        {' '}→ โอกาสชนะ <span className="p-fg-accent" style={{ fontWeight: 600 }}>~80%</span>
        <span className="p-fg-dim"> · </span>
        ลด ~{band.disc_p50}% <span className="p-mono">(≈{fmtBaht(band.price_p50)} บ.)</span>
        {' '}→ <span className="p-fg-accent">~50%</span>
      </div>
      <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 6, lineHeight: 1.5 }}>
        จากประวัติผลประมูลจริงในภูมิภาคนี้ 27,000+ งาน — ตัวช่วยประกอบการตัดสินใจ ไม่ใช่ราคาแนะนำ
      </div>
    </div>
  );
}

// ── Calculator (คำนวณโอกาสชนะเจาะจงคู่แข่ง) ───────────────────────────────────

function CalcSection({ pid, tables }: { pid: string; tables: CompanyTable[] }) {
  const seen = new Set<string>();
  const options: { name: string; games: number; median: number | null }[] = [];
  for (const blk of tables) {
    for (const c of blk.companies || []) {
      const core = normName(c.name);
      if (core && !seen.has(core)) {
        seen.add(core);
        options.push({ name: c.name, games: c.games, median: c.median ?? null });
      }
    }
  }

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [extraNames, setExtraNames] = useState('');
  const [myPrice, setMyPrice] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<CustomCalc | null>(null);
  const [noResult, setNoResult] = useState(false);

  const toggle = (name: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  };

  const calc = async () => {
    setLoading(true); setError(''); setNoResult(false);
    try {
      const r = await fetch('/api/portal/job-calc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pid,
          my_price: myPrice,
          selected_names: [...selected],
          extra_names: extraNames.split('\n').map(s => s.trim()).filter(Boolean),
        }),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error('calc failed');
      if (data.custom_calc) setResult(data.custom_calc);
      else { setResult(null); setNoResult(true); }
    } catch {
      setError('คำนวณไม่สำเร็จ — ลองอีกครั้ง');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-card">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {options.map(o => (
          <label key={o.name} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13.5, cursor: 'pointer', lineHeight: 1.5 }}>
            <input type="checkbox" checked={selected.has(o.name)} onChange={() => toggle(o.name)}
              style={{ marginTop: 3, accentColor: 'var(--accent)' }} />
            <span>
              {o.name}
              {o.median != null && <span className="p-fg-dim"> (ชนะ {o.games} งาน, ลดเฉลี่ย {Math.round(o.median)}%)</span>}
            </span>
          </label>
        ))}
      </div>
      <div className="p-label" style={{ marginTop: 14 }}>หรือพิมพ์ชื่อบริษัทอื่นเพิ่ม (1 ชื่อ/บรรทัด)</div>
      <textarea className="p-input" rows={2} value={extraNames} onChange={e => setExtraNames(e.target.value)}
        style={{ resize: 'vertical', fontFamily: 'var(--font-sans)' }} />
      <div className="p-label" style={{ marginTop: 12 }}>ราคาที่จะยื่น (บาท)</div>
      <input className="p-input" type="number" min={1} step={1} value={myPrice} onChange={e => setMyPrice(e.target.value)} />
      <button className="p-btn p-btn-primary" onClick={calc} disabled={loading || !myPrice}
        style={{ width: '100%', marginTop: 12 }}>
        {loading ? 'กำลังคำนวณ…' : '🎯 คำนวณโอกาสชนะ'}
      </button>
      {error && <div style={{ color: 'var(--wine-soft)', fontSize: 12.5, marginTop: 8 }}>{error}</div>}
      {noResult && (
        <div className="p-fg-mute" style={{ fontSize: 12.5, marginTop: 8 }}>
          เลือกคู่แข่งอย่างน้อย 1 บริษัท หรือกรอกราคาให้ถูกต้อง
        </div>
      )}
      {result && (
        <div className="p-gilt" style={{ marginTop: 14, padding: 14 }}>
          <div className="p-display" style={{ fontSize: 20 }}>
            🎯 โอกาสชนะของคุณรวม: <span style={{ color: 'var(--accent)' }}>{result.overall_win_pct}%</span>
          </div>
          <div className="p-fg-mute" style={{ fontSize: 12.5, marginTop: 2 }}>ราคาของคุณ = ลด {result.my_discount_pct}%</div>
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {result.breakdown.map((b, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13, borderTop: '1px solid var(--line)', paddingTop: 6 }}>
                <span style={{ minWidth: 0 }}>{b.name}{b.source ? <span className="p-fg-dim"> ({b.source})</span> : null}</span>
                <span className="p-mono" style={{ whiteSpace: 'nowrap' }}>ชนะคุณ ~{b.win_pct_against}%</span>
              </div>
            ))}
          </div>
          <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 10, lineHeight: 1.6 }}>
            *โอกาส% ประเมินจากนิสัยการยื่นราคาของคู่แข่งในงานประเภท+หน่วยงานแบบเดียวกัน (โมเดล Gates) — เป็นการประมาณ ไม่ใช่การรับประกัน
          </div>
        </div>
      )}
    </div>
  );
}

// ── Bidders (ผู้ยื่นทั้งหมด) ──────────────────────────────────────────────────

function BiddersSection({ bidders }: { bidders: JobDetail['bidders'] }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {bidders.map((b, i) => {
        const name = b.name || '(ไม่ระบุชื่อ)';
        return (
          <div key={i} className="p-card" style={{
            padding: '12px 14px', display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center',
            borderColor: b.is_winner ? 'var(--accent-deep)' : 'var(--border)',
            background: b.is_winner ? 'var(--gold-glow)' : 'var(--surface)',
          }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: 13.5, lineHeight: 1.45, display: 'flex', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
                <span className="p-mono p-fg-dim" style={{ fontSize: 11 }}>{i + 1}.</span>
                {b.is_winner && <span>🏆</span>}
                {b.href
                  ? <a href={b.href} className="p-fg-accent" style={{ textDecoration: 'none' }}>{name}</a>
                  : <span>{name}</span>}
                {b.is_sme && <Chip tone="emerald">SME</Chip>}
              </div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div className="p-serif" style={{ fontSize: 15, fontWeight: 500 }}>{fmtBaht(b.price)}</div>
              <div className="p-fg-dim" style={{ fontSize: 11 }}>
                {b.discount != null ? `ส่วนลด ${b.discount.toFixed(1)}%` : '—'}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Overview note (โน้ตภาพรวม) ────────────────────────────────────────────────

function OverviewSection({ pid, initial }: { pid: string; initial: string }) {
  const [text, setText] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState('');

  const save = async () => {
    setSaving(true); setError('');
    try {
      const r = await fetch('/api/portal/job-note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid, action: 'save_overview', note: text }),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error('save failed');
      setSavedAt(Date.now());
    } catch {
      setError('บันทึกไม่สำเร็จ — ลองอีกครั้ง');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-card">
      <textarea className="p-input" rows={4} value={text} onChange={e => { setText(e.target.value); setSavedAt(null); }}
        placeholder="จดภาพรวมงานนี้ เช่น คนติดต่อ งบ เงื่อนไข จุดเด่น..."
        style={{ resize: 'vertical', fontFamily: 'var(--font-sans)' }} />
      <button className="p-btn p-btn-primary" onClick={save} disabled={saving}
        style={{ marginTop: 10, height: 38, padding: '0 16px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
        <Icons.Check size={14} />{saving ? 'กำลังบันทึก…' : savedAt ? 'บันทึกแล้ว' : 'บันทึกโน้ต'}
      </button>
      {error && <div style={{ color: 'var(--wine-soft)', fontSize: 12.5, marginTop: 8 }}>{error}</div>}
    </div>
  );
}

// ── Timeline (ไทม์ไลน์ของฉัน) ─────────────────────────────────────────────────

function TimelineSection({ pid, initialNotes }: { pid: string; initialNotes: JobNote[] }) {
  const [notes, setNotes] = useState<JobNote[]>(initialNotes);
  const [newDate, setNewDate] = useState('');
  const [newText, setNewText] = useState('');
  const [editId, setEditId] = useState<number | null>(null);
  const [editDate, setEditDate] = useState('');
  const [editText, setEditText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const post = async (body: Record<string, unknown>) => {
    setBusy(true); setError('');
    try {
      const r = await fetch('/api/portal/job-note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid, ...body }),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error('note failed');
      setNotes(data.notes ?? []);
      return true;
    } catch {
      setError('บันทึกไม่สำเร็จ — ลองอีกครั้ง');
      return false;
    } finally {
      setBusy(false);
    }
  };

  const fmtDate = (s: string) => {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    return d.toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: '2-digit' });
  };

  return (
    <div className="p-card">
      {/* เพิ่มรายการ */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input className="p-input" type="date" value={newDate} onChange={e => setNewDate(e.target.value)} style={{ width: 150, flexShrink: 0 }} />
        <input className="p-input" value={newText} onChange={e => setNewText(e.target.value)}
          placeholder="สิ่งที่จะทำ เช่น โทรหาช่าง" style={{ flex: 1, minWidth: 160 }} />
        <button className="p-btn p-btn-primary" disabled={busy || !newDate || !newText.trim()}
          onClick={async () => {
            if (await post({ action: 'add', entry_date: newDate, note: newText.trim() })) { setNewDate(''); setNewText(''); }
          }}
          style={{ height: 40, padding: '0 14px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 5 }}>
          <Icons.Plus size={14} />เพิ่ม
        </button>
      </div>
      {error && <div style={{ color: 'var(--wine-soft)', fontSize: 12.5, marginTop: 8 }}>{error}</div>}

      {notes.length === 0 ? (
        <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 13.5, marginTop: 14 }}>
          ยังไม่มีรายการ — เพิ่มด้านบนได้เลยครับ
        </div>
      ) : (
        <div style={{ marginTop: 14, borderLeft: '2px solid var(--border)', paddingLeft: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {notes.map(nt => (
            <div key={nt.id} style={{ position: 'relative' }}>
              <span style={{ position: 'absolute', left: -19.5, top: 5, color: 'var(--accent)' }}><Diamond size={4.5} /></span>
              {editId === nt.id ? (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  <input className="p-input" type="date" value={editDate} onChange={e => setEditDate(e.target.value)} style={{ width: 145, flexShrink: 0, padding: '7px 10px', fontSize: 13 }} />
                  <input className="p-input" value={editText} onChange={e => setEditText(e.target.value)} style={{ flex: 1, minWidth: 140, padding: '7px 10px', fontSize: 13 }} />
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button className="p-icon-btn" title="บันทึก" disabled={busy}
                      onClick={async () => {
                        if (await post({ action: 'edit', note_id: nt.id, entry_date: editDate, note: editText.trim() })) setEditId(null);
                      }}>
                      <Icons.Check size={16} style={{ color: 'var(--emerald)' }} />
                    </button>
                    <button className="p-icon-btn" title="ยกเลิก" onClick={() => setEditId(null)}><Icons.X size={16} /></button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
                  <div style={{ minWidth: 0 }}>
                    <div className="p-mono p-fg-dim" style={{ fontSize: 10.5, letterSpacing: '0.05em' }}>{fmtDate(nt.entry_date)}</div>
                    <div style={{ fontSize: 13.5, lineHeight: 1.5, marginTop: 2 }}>{nt.note}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
                    <button className="p-icon-btn" title="แก้ไข" style={{ width: 30, height: 30 }}
                      onClick={() => { setEditId(nt.id); setEditDate(nt.entry_date.slice(0, 10)); setEditText(nt.note); }}>
                      <Icons.Edit size={14} />
                    </button>
                    <button className="p-icon-btn" title="ลบ" style={{ width: 30, height: 30 }} disabled={busy}
                      onClick={() => post({ action: 'delete', note_id: nt.id })}>
                      <Icons.Trash size={14} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function JobDetailClient({ pid, detail, engineDown }: { pid: string; detail: JobDetail | null; engineDown: boolean }) {
  const router = useRouter();
  const [starred, setStarred] = useState(detail?.starred ?? false);

  const toggleStar = async () => {
    const prev = starred;
    setStarred(!prev);
    try {
      await fetch('/api/portal/star', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: pid }),
      });
    } catch {
      setStarred(prev); // revert on failure
    }
  };

  if (!detail) {
    return (
      <div className="p-enter">
        <TopBar title="รายละเอียดงาน" subtitle={pid} onLeft={() => router.back()} />
        <div className="p-page p-page-topbar">
          <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
              {engineDown ? 'ดึงข้อมูลไม่ได้ชั่วคราว — ลองใหม่อีกครั้งครับ' : 'ไม่พบรายละเอียดงานนี้'}
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

  const j = detail.job;
  const dl = daysLeftOf(j.deadline);
  const urgency = dl === null ? 'outline' : dl <= 5 ? 'wine' : dl <= 10 ? 'gold' : 'outline';
  const hasIntel = !!detail.company_tables?.length;

  return (
    <div className="p-enter">
      <TopBar
        title="รายละเอียดงาน"
        subtitle={j.project_id}
        onLeft={() => router.back()}
        right={
          <button className="p-icon-btn" onClick={toggleStar} title="ที่สนใจ"
            style={{ color: starred ? 'var(--accent)' : 'var(--fg-dim)', fontSize: 20 }}>
            {starred ? '★' : '☆'}
          </button>
        }
      />

      <div className="p-page p-page-topbar">
        {/* หัวงาน */}
        <div className="p-gilt">
          {j.location && <div className="p-mono p-fg-mute" style={{ fontSize: 11, letterSpacing: '0.04em', marginBottom: 6 }}>📍 {j.location}</div>}
          <div className="p-display" style={{ fontSize: 19, lineHeight: 1.35 }}>{j.name}</div>
          <div style={{ display: 'flex', gap: 16, marginTop: 14, alignItems: 'center', flexWrap: 'wrap' }}>
            {j.budget > 0 && (
              <div>
                <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>ราคากลาง</div>
                <div className="p-serif" style={{ fontSize: 19, fontWeight: 500 }}>
                  <span className="p-fg-accent">{fmtBaht(j.budget)}</span> <span className="p-fg-dim" style={{ fontSize: 11 }}>บาท</span>
                </div>
              </div>
            )}
            {j.pred_lo && j.pred_hi ? (
              <div style={{ paddingLeft: 16, borderLeft: '1px solid var(--line)' }}>
                <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em' }}>คาดราคาเสนอ</div>
                <div className="p-serif" style={{ fontSize: 14 }}>{fmtBaht(j.pred_lo)}–{fmtBaht(j.pred_hi)}</div>
              </div>
            ) : null}
          </div>
          {j.deadline && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
              <span className="p-fg-mute" style={{ fontSize: 12 }}>⏰ ยื่นซอง {j.deadline}{j.deadline_time ? ` ${j.deadline_time}` : ''}</span>
              {dl !== null && <Chip tone={urgency} icon={<Icons.Clock size={11} />}>เหลือ {dl} วัน</Chip>}
            </div>
          )}
        </div>

        {/* คู่แข่ง */}
        {hasIntel && (
          <>
            <SectionHead smallcaps="Competitors" title="🏢 คู่แข่งในสนามนี้" />
            <CompanyTables tables={detail.company_tables!} />
          </>
        )}

        {/* โอกาสชนะตามจำนวนผู้ยื่น */}
        {detail.winrate_table && (
          <>
            <SectionHead smallcaps="Win Probability" title="💵 โอกาสชนะตามจำนวนผู้ยื่น"
              right={<Chip tone="gold" icon={<Diamond size={5} />}>งบ {fmtBaht(detail.winrate_table.budget)}</Chip>} />
            <WinrateSection wt={detail.winrate_table} />
          </>
        )}

        {/* แถบส่วนลดจากสถิติ (ML) — มีหัวข้อเองเมื่อไม่มีตาราง winrate */}
        {detail.ml_band && (
          <>
            {!detail.winrate_table && (
              <SectionHead smallcaps="Win Probability" title="💵 โอกาสชนะจากสถิติพื้นที่" />
            )}
            <MlBandCard band={detail.ml_band} />
          </>
        )}

        {/* เครื่องคำนวณ */}
        {hasIntel && (
          <>
            <SectionHead smallcaps="Calculator" title="🎯 คำนวณโอกาสชนะเจาะจงคู่แข่ง" />
            <CalcSection pid={pid} tables={detail.company_tables!} />
          </>
        )}

        {/* ผู้ยื่นทั้งหมด */}
        <SectionHead smallcaps="Bidders" title="ผู้ยื่นทั้งหมด"
          right={detail.bidders.length > 0 ? <Chip tone="gold" icon={<Diamond size={5} />}>{detail.bidders.length} ราย</Chip> : undefined} />
        {detail.bidders.length === 0 ? (
          <div className="p-card" style={{ textAlign: 'center', padding: 24 }}>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 13.5 }}>
              งานนี้ยังไม่มีข้อมูลผู้ยื่น — รอประมูล/ประกาศผลครับ
            </div>
          </div>
        ) : (
          <BiddersSection bidders={detail.bidders} />
        )}

        {/* โน้ตภาพรวม */}
        <SectionHead smallcaps="My Notes" title="📝 โน้ตภาพรวม" />
        <OverviewSection pid={pid} initial={detail.overview} />

        {/* ไทม์ไลน์ */}
        <SectionHead smallcaps="My Timeline" title="🚂 ไทม์ไลน์ของฉัน" />
        <TimelineSection pid={pid} initialNotes={detail.notes} />
      </div>
    </div>
  );
}
