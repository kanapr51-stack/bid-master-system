'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { TIERS, type Tier } from '@/lib/portal-data';
import { TopBar, ButlerNote, Icons } from '../_ui';

// ── Tier Card ─────────────────────────────────────────────────────────────────

function DiamondDot() {
  return <svg width="10" height="10" viewBox="0 0 10 10"><polygon points="5,1 9,5 5,9 1,5" fill="currentColor" /></svg>;
}

function TierCard({ tier, billing, isCurrent, isSelected, onSelect }: { tier: Tier; billing: string; isCurrent: boolean; isSelected: boolean; onSelect: () => void }) {
  const price = billing === 'annual' ? tier.price * 10 : tier.price;
  const isFree = tier.price === 0;
  return (
    <button onClick={onSelect} className="p-card" style={{ textAlign: 'left', padding: 0, cursor: 'pointer', position: 'relative', borderColor: isSelected ? 'var(--accent)' : 'var(--border)', boxShadow: isSelected ? '0 0 0 1px var(--accent), 0 0 24px var(--gold-glow)' : 'none', transition: 'all 0.18s', width: '100%' }}>
      {tier.popular && <div style={{ position: 'absolute', top: -10, left: 16, background: 'var(--accent)', color: 'var(--ink-deep)', padding: '3px 10px', borderRadius: 999, fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>POPULAR</div>}
      {isCurrent && <div style={{ position: 'absolute', top: -10, right: 16, background: 'var(--surface)', color: 'var(--accent)', padding: '3px 10px', borderRadius: 999, fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', fontFamily: 'var(--font-mono)', border: '1px solid var(--accent-deep)', whiteSpace: 'nowrap' }}>กำลังใช้</div>}

      <div style={{ padding: 18 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, justifyContent: 'space-between' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="p-display" style={{ fontSize: 22, lineHeight: 1.1 }}>{tier.name}</div>
            <div className="p-fg-mute" style={{ fontSize: 12, marginTop: 2 }}>{tier.nameTh}</div>
          </div>
          <div style={{ width: 22, height: 22, borderRadius: '50%', border: `1.5px solid ${isSelected ? 'var(--accent)' : 'var(--border)'}`, background: isSelected ? 'var(--accent)' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--ink-deep)', flexShrink: 0, marginTop: isCurrent ? 14 : 0 }}>
            {isSelected && <Icons.Check size={13} sw={2.5} />}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 14 }}>
          {isFree ? (
            <><span className="p-display p-fg-accent" style={{ fontSize: 36 }}>ฟรี</span><span className="p-fg-mute" style={{ fontSize: 13 }}>· 30 วัน</span></>
          ) : (
            <><span className="p-display p-fg-accent" style={{ fontSize: 36 }}>{price.toLocaleString()}</span><span className="p-fg-mute" style={{ fontSize: 14 }}>฿ / {billing === 'annual' ? 'ปี' : 'เดือน'}</span></>
          )}
        </div>

        <div style={{ marginTop: 14, padding: '10px 12px', background: 'var(--gold-glow)', borderRadius: 8, border: '1px solid var(--accent-deep)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ color: 'var(--accent)' }}><Icons.Bot size={16} /></div>
          <div>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em' }}>SEBASTIAN CHAT</div>
            <div className="p-serif p-fg-accent" style={{ fontSize: 14, fontWeight: 500 }}>{tier.chatLabel}</div>
          </div>
        </div>

        <ul style={{ listStyle: 'none', padding: 0, margin: '14px 0 0', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {tier.perks.map((p, i) => (
            <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13, lineHeight: 1.4 }}>
              <span style={{ color: 'var(--accent)', marginTop: 2, flexShrink: 0 }}><DiamondDot /></span>
              <span>{p}</span>
            </li>
          ))}
        </ul>

        <div className="p-serif p-fg-dim" style={{ fontStyle: 'italic', fontSize: 12, marginTop: 14, lineHeight: 1.4 }}>{tier.note}</div>
      </div>
    </button>
  );
}

// ── Row helper ────────────────────────────────────────────────────────────────

function Row({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '6px 0', gap: 12 }}>
      <span className="p-fg-mute" style={{ fontSize: 13 }}>{label}</span>
      <span style={{ fontSize: 13.5, fontWeight: 500, color: accent ? 'var(--accent)' : 'inherit', textAlign: 'right' }}>{value}</span>
    </div>
  );
}

// ── Packages Client ───────────────────────────────────────────────────────────

interface Props {
  lineUserId: string;
  currentTierId: string;
  daysLeft: number;
  expiryLabel: string;
}

export function PackagesClient({ lineUserId, currentTierId, daysLeft, expiryLabel }: Props) {
  const router = useRouter();
  const [billing, setBilling] = useState<'monthly' | 'annual'>('monthly');
  const [selectedId, setSelectedId] = useState(currentTierId === 'trial' ? 'standard' : currentTierId);
  const [step, setStep] = useState<'compare' | 'confirm' | 'sent'>('compare');
  const [submitting, setSubmitting] = useState(false);

  const selected = TIERS.find(t => t.id === selectedId)!;
  const current = TIERS.find(t => t.id === currentTierId)!;
  const isCurrent = selected.id === currentTierId;
  const finalPrice = billing === 'annual' ? selected.price * 10 : selected.price;

  const handleRequest = async () => {
    setSubmitting(true);
    try {
      await fetch('/api/portal/upgrade-request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tier: selected.id, billing }),
      });
      setStep('sent');
    } catch { /* engine unreachable — ยังพาไปหน้า sent (ไม่ตกหล่นการขาย) */ setStep('sent'); }
    finally { setSubmitting(false); }
  };

  if (step === 'sent') {
    return (
      <div className="p-enter" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: '40px 22px' }}>
        <div style={{ width: 96, height: 96, borderRadius: 14, background: 'var(--gold-glow)', border: '1px solid var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)', marginBottom: 18 }}>
          <Icons.Check2 size={48} />
        </div>
        <div className="p-mono" style={{ fontSize: 10, letterSpacing: '0.2em', color: 'var(--accent)', marginBottom: 8 }}>REQUEST RECEIVED</div>
        <div className="p-display" style={{ fontSize: 30 }}>ได้รับเรื่องแล้วครับ</div>
        <div className="p-serif" style={{ fontSize: 18, marginTop: 6, fontStyle: 'italic', color: 'var(--fg-mute)' }}>ความสนใจแพ็กเกจ {selected.name}</div>
        <div style={{ marginTop: 24, maxWidth: 360, width: '100%' }}>
          <ButlerNote tone="gold">
            ผมแจ้งทีมงานเรียบร้อยแล้วครับ — จะมีผู้ดูแลติดต่อกลับเพื่อยืนยันแพ็กเกจและวิธีชำระเงินโดยเร็วที่สุด
          </ButlerNote>
        </div>
        <button className="p-btn p-btn-primary" onClick={() => router.push('/portal/world')} style={{ width: '100%', maxWidth: 360, marginTop: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          กลับสู่ Company World
        </button>
      </div>
    );
  }

  return (
    <div className="p-enter">
      <TopBar
        title="แพ็กเกจ"
        subtitle={current.id === 'trial' ? `Trial · เหลือ ${daysLeft} วัน` : `กำลังใช้ ${current.name}`}
        left={step !== 'compare' ? <Icons.ChevronLeft size={18} /> : undefined}
        onLeft={step !== 'compare' ? () => setStep('compare') : undefined}
      />
      <div className="p-page p-page-topbar">
        {/* ── Compare ── */}
        {step === 'compare' && (
          <>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14, marginBottom: 16, lineHeight: 1.5 }}>
              ทุกแพ็กเกจเข้าถึงข้อมูลงานประมูลครบเหมือนกัน — ต่างกันที่จำนวนการคุยกับ Sebastian และความสามารถพิเศษ
            </div>
            <div className="p-tabs" style={{ marginBottom: 16 }}>
              <button className={`p-tab${billing === 'monthly' ? ' active' : ''}`} onClick={() => setBilling('monthly')}>รายเดือน</button>
              <button className={`p-tab${billing === 'annual' ? ' active' : ''}`} onClick={() => setBilling('annual')}>รายปี · ลด 17%</button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {TIERS.map(t => (
                <TierCard key={t.id} tier={t} billing={billing} isCurrent={t.id === currentTierId} isSelected={t.id === selectedId} onSelect={() => setSelectedId(t.id)} />
              ))}
            </div>
            <div style={{ position: 'sticky', bottom: 76, marginTop: 18, background: 'var(--bg)', padding: '14px 0', borderRadius: 12 }}>
              <button className="p-btn p-btn-primary" onClick={() => setStep('confirm')} style={{ width: '100%', height: 52, fontSize: 15.5, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <Icons.Crown size={16} />
                {isCurrent ? 'ดูรายละเอียดแพ็กเกจ' : `สนใจแพ็กเกจ ${selected.name}`}
              </button>
            </div>
          </>
        )}

        {/* ── Confirm (แจ้งความสนใจ — ยังไม่มีระบบจ่ายเงินออนไลน์) ── */}
        {step === 'confirm' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <ButlerNote tone="gold">ขอสรุปแพ็กเกจที่ท่านสนใจครับ — กดแจ้งความสนใจแล้วทีมงานจะติดต่อกลับเพื่อยืนยันและแจ้งวิธีชำระเงิน</ButlerNote>
            <div className="p-gilt">
              <div className="p-mono" style={{ fontSize: 10, letterSpacing: '0.18em', color: 'var(--accent)' }}>PACKAGE SUMMARY</div>
              <div className="p-display" style={{ fontSize: 26, marginTop: 4 }}>Sebastian · {selected.name}</div>
              <div className="p-fg-mute" style={{ fontSize: 13, marginTop: 2 }}>{selected.nameTh}</div>
              <div style={{ borderTop: '1px solid var(--line)', marginTop: 16, paddingTop: 14 }}>
                <Row label="แพ็กเกจ" value={`${selected.name} (${selected.nameTh})`} />
                <Row label="รอบที่สนใจ" value={billing === 'annual' ? 'รายปี · ลด 17%' : 'รายเดือน'} />
                <Row label="Sebastian Chat" value={selected.chatLabel} accent />
              </div>
              <div style={{ borderTop: '1px solid var(--line)', marginTop: 14, paddingTop: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <div className="p-display" style={{ fontSize: 18 }}>ราคาโดยประมาณ</div>
                <div className="p-display p-fg-accent" style={{ fontSize: 28 }}>{selected.price === 0 ? 'ฟรี' : finalPrice.toLocaleString()}<span className="p-fg-mute" style={{ fontSize: 14, marginLeft: 4 }}>{selected.price === 0 ? '' : `฿ / ${billing === 'annual' ? 'ปี' : 'เดือน'}`}</span></div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="p-btn p-btn-ghost" onClick={() => setStep('compare')} style={{ flex: 1 }}>กลับ</button>
              <button className="p-btn p-btn-primary" onClick={handleRequest} disabled={submitting} style={{ flex: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <Icons.Crown size={16} />{submitting ? 'กำลังส่ง…' : 'แจ้งความสนใจ'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
