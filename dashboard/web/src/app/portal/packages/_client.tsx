'use client';

import { useState, useEffect } from 'react';
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

// ── Pay View ──────────────────────────────────────────────────────────────────

function PayView({ tier, finalPrice, billing, onDone }: { tier: Tier; finalPrice: number; billing: string; onDone: () => void }) {
  const [seconds, setSeconds] = useState(300);
  useEffect(() => {
    const t = setInterval(() => setSeconds(s => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, []);
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0');
  const ss = String(seconds % 60).padStart(2, '0');
  const ref = `SB-2026-${Math.floor(Math.random() * 9000 + 1000)}`;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18, alignItems: 'center', textAlign: 'center' }}>
      <div className="p-mono" style={{ fontSize: 10, letterSpacing: '0.18em', color: 'var(--accent)' }}>PROMPTPAY QR</div>
      <div className="p-display" style={{ fontSize: 24 }}>สแกนเพื่อชำระ {Math.round(finalPrice * 1.07).toLocaleString()} ฿</div>
      <div className="p-gilt" style={{ background: 'var(--surface)', padding: 24 }}>
        <div className="p-qr"><span className="p-mono p-fg-dim" style={{ fontSize: 12 }}>QR Code</span></div>
        <div className="p-mono" style={{ fontSize: 11, letterSpacing: '0.08em', marginTop: 16, color: 'var(--fg-mute)', textAlign: 'center' }}>
          QR หมดอายุใน <span style={{ color: 'var(--accent)', fontSize: 16, fontWeight: 600 }}>{mm}:{ss}</span>
        </div>
      </div>
      <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div className="p-card" style={{ padding: '8px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="p-fg-mute" style={{ fontSize: 12 }}>เลขที่อ้างอิง</span>
          <span className="p-mono" style={{ fontSize: 12.5, letterSpacing: '0.04em' }}>{ref}</span>
        </div>
        <div className="p-card" style={{ padding: '8px 14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="p-fg-mute" style={{ fontSize: 12 }}>ผู้รับเงิน</span>
          <span style={{ fontSize: 12.5 }}>Manor Master System Co., Ltd.</span>
        </div>
      </div>
      <button className="p-btn p-btn-primary" onClick={onDone} style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
        <Icons.Check size={16} />ยืนยันว่าชำระแล้ว (Demo)
      </button>
      <div className="p-fg-dim" style={{ fontSize: 11.5, fontStyle: 'italic' }}>ระบบจะตรวจสอบและยืนยันอัตโนมัติภายใน 30 วินาที</div>
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
  const [step, setStep] = useState<'compare' | 'confirm' | 'pay' | 'success'>('compare');

  const selected = TIERS.find(t => t.id === selectedId)!;
  const current = TIERS.find(t => t.id === currentTierId)!;
  const isCurrent = selected.id === currentTierId;
  const finalPrice = billing === 'annual' ? selected.price * 10 : selected.price;

  const handleUpgrade = async () => {
    // Persist tier change
    await fetch('/api/portal/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tierId: selected.id }),
    }).catch(() => {});
    setStep('success');
  };

  if (step === 'success') {
    return (
      <div className="p-enter" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: '40px 22px' }}>
        <div style={{ width: 96, height: 96, borderRadius: 14, background: 'var(--gold-glow)', border: '1px solid var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)', marginBottom: 18 }}>
          <Icons.Check2 size={48} />
        </div>
        <div className="p-mono" style={{ fontSize: 10, letterSpacing: '0.2em', color: 'var(--accent)', marginBottom: 8 }}>PAYMENT SUCCESS</div>
        <div className="p-display" style={{ fontSize: 30 }}>ยินดีต้อนรับท่าน</div>
        <div className="p-serif" style={{ fontSize: 18, marginTop: 6, fontStyle: 'italic', color: 'var(--fg-mute)' }}>สู่ Sebastian · {selected.name}</div>
        <div style={{ marginTop: 24, maxWidth: 360, width: '100%' }}>
          <ButlerNote tone="gold">
            ผมพร้อมรับใช้ท่านเต็มที่แล้วครับ — ตั้งแต่บัดนี้เป็นต้นไป ท่านสามารถปรึกษาผมใน LINE ได้ {selected.chatLabel}
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
                {isCurrent ? 'ดูรายละเอียดแพ็กเกจ' : `เปลี่ยนเป็น ${selected.name}`}
              </button>
            </div>
          </>
        )}

        {/* ── Confirm ── */}
        {step === 'confirm' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <ButlerNote tone="gold">ขอสรุปแพ็กเกจที่ท่านเลือกครับ — โปรดตรวจสอบรายละเอียดก่อนชำระเงิน</ButlerNote>
            <div className="p-gilt">
              <div className="p-mono" style={{ fontSize: 10, letterSpacing: '0.18em', color: 'var(--accent)' }}>ORDER SUMMARY</div>
              <div className="p-display" style={{ fontSize: 26, marginTop: 4 }}>Sebastian · {selected.name}</div>
              <div className="p-fg-mute" style={{ fontSize: 13, marginTop: 2 }}>{selected.nameTh} · {billing === 'annual' ? 'ชำระรายปี' : 'ชำระรายเดือน'}</div>
              <div style={{ borderTop: '1px solid var(--line)', marginTop: 16, paddingTop: 14 }}>
                <Row label="แพ็กเกจ" value={`${selected.name} (${selected.nameTh})`} />
                <Row label="รอบบิล" value={billing === 'annual' ? 'รายปี · ลด 17%' : 'รายเดือน'} />
                <Row label="Sebastian Chat" value={selected.chatLabel} accent />
                <Row label="VAT 7%" value={`${Math.round(finalPrice * 0.07).toLocaleString()} ฿`} />
              </div>
              <div style={{ borderTop: '1px solid var(--line)', marginTop: 14, paddingTop: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <div className="p-display" style={{ fontSize: 18 }}>ยอดชำระทั้งหมด</div>
                <div className="p-display p-fg-accent" style={{ fontSize: 32 }}>{Math.round(finalPrice * 1.07).toLocaleString()}<span className="p-fg-mute" style={{ fontSize: 14, marginLeft: 4 }}>฿</span></div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="p-btn p-btn-ghost" onClick={() => setStep('compare')} style={{ flex: 1 }}>กลับ</button>
              <button className="p-btn p-btn-primary" onClick={() => selected.price === 0 ? handleUpgrade() : setStep('pay')} style={{ flex: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <Icons.Coin size={16} />ดำเนินการชำระเงิน
              </button>
            </div>
          </div>
        )}

        {/* ── Pay ── */}
        {step === 'pay' && <PayView tier={selected} finalPrice={finalPrice} billing={billing} onDone={handleUpgrade} />}
      </div>
    </div>
  );
}
