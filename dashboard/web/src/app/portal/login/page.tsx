'use client';

import { useState } from 'react';
import { TIERS } from '@/lib/portal-data';

// ── SVG Components ────────────────────────────────────────────────────────────

function Crest({ size = 76 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 76" fill="none" aria-label="Sebastian crest">
      <path d="M32 2 L58 14 L58 40 C58 54 46 66 32 74 C18 66 6 54 6 40 L6 14 Z" stroke="currentColor" strokeWidth="1.5" fill="none" />
      <path d="M32 2 L58 14 L58 40 C58 54 46 66 32 74 C18 66 6 54 6 40 L6 14 Z" fill="currentColor" fillOpacity="0.06" />
      <text x="32" y="48" textAnchor="middle" fontSize="28" fontFamily="var(--font-display, serif)" fontWeight="600" fill="currentColor" style={{ letterSpacing: '-0.02em' }}>S</text>
      <line x1="18" y1="30" x2="46" y2="30" stroke="currentColor" strokeWidth="0.75" opacity="0.5" />
      <circle cx="32" cy="24" r="3" fill="currentColor" fillOpacity="0.5" />
    </svg>
  );
}

function BellIcon({ size = 11 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>;
}

function DocIcon({ size = 11 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>;
}

function TrendIcon({ size = 11 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>;
}

function DiamondShape({ size = 5 }: { size?: number }) {
  return <svg width={size * 2} height={size * 2} viewBox="0 0 10 10"><polygon points="5,1 9,5 5,9 1,5" fill="currentColor"/></svg>;
}

function XIcon({ size = 16 }: { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>;
}

function LineLogoIcon({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm-2.6 11.4c-.55.62-3.55 4-3.95 4.36-.4.36-.65.21-.65-.2 0-.41.04-1.32.04-1.32-2.7-.35-4.84-2.31-4.84-4.69 0-2.62 2.6-4.75 5.8-4.75s5.8 2.13 5.8 4.75c0 1.07-.43 2.05-1.2 2.85z" />
    </svg>
  );
}

// ── Divider ornament ──────────────────────────────────────────────────────────

function DividerOrnate() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: 'var(--fg-dim)', width: '100%', maxWidth: 240 }}>
      <div style={{ flex: 1, height: 1, background: 'var(--line)' }} />
      <DiamondShape size={4} />
      <div style={{ flex: 1, height: 1, background: 'var(--line)' }} />
      <DiamondShape size={3} />
      <div style={{ flex: 1, height: 1, background: 'var(--line)' }} />
    </div>
  );
}

// ── Tier Modal ────────────────────────────────────────────────────────────────

function TierModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="p-scrim" onClick={onClose}>
      <div className="p-modal" onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div className="p-display" style={{ fontSize: 22 }}>แพ็กเกจของเรา</div>
          <button className="p-icon-btn" onClick={onClose}><XIcon /></button>
        </div>
        <p className="p-serif p-fg-mute" style={{ fontStyle: 'italic', marginBottom: 16, fontSize: 14, lineHeight: 1.6 }}>
          ทุกแพ็กเกจเข้าถึงข้อมูลงานประมูลครบเหมือนกัน ต่างกันที่จำนวนการคุยกับ Sebastian และความสามารถพิเศษ
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {TIERS.map(t => (
            <div key={t.id} className="p-card" style={{ padding: 14, borderColor: t.popular ? 'var(--accent)' : 'var(--border)', position: 'relative' }}>
              {t.popular && (
                <div style={{ position: 'absolute', top: -8, right: 12, background: 'var(--accent)', color: 'var(--ink-deep)', padding: '2px 10px', borderRadius: 999, fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', fontFamily: 'var(--font-mono)' }}>POPULAR</div>
              )}
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
                <div className="p-display" style={{ fontSize: 18 }}>{t.name}</div>
                <div className="p-mono p-fg-accent" style={{ fontSize: 13 }}>{t.priceLabel}</div>
              </div>
              <div className="p-fg-mute" style={{ fontSize: 12, marginTop: 2 }}>{t.nameTh}</div>
              <div className="p-fg-dim" style={{ fontSize: 11.5, marginTop: 8, fontFamily: 'var(--font-mono)' }}>
                Sebastian Chat: <span style={{ color: 'var(--accent)' }}>{t.chatLabel}</span>
              </div>
            </div>
          ))}
        </div>
        <a href="/api/auth/line" style={{ display: 'block', marginTop: 16 }}>
          <button className="p-btn p-btn-primary" style={{ width: '100%', height: 48, fontSize: 15 }}>
            เริ่มต้นใช้งานฟรี 30 วัน
          </button>
        </a>
      </div>
    </div>
  );
}

// ── Login Page ────────────────────────────────────────────────────────────────

export default function LoginPage() {
  const [showTiers, setShowTiers] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleLogin = () => {
    setLoading(true);
    window.location.href = '/api/auth/line';
  };

  return (
    <div className="p-enter" style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', padding: '32px 22px 28px' }}>
      {/* Top ornament */}
      <div style={{ display: 'flex', justifyContent: 'center', marginTop: 8 }}>
        <DividerOrnate />
      </div>

      {/* Hero */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', textAlign: 'center', padding: '32px 0' }}>
        <div style={{ color: 'var(--accent)', display: 'flex', justifyContent: 'center', marginBottom: 18 }}>
          <Crest size={76} />
        </div>
        <div className="p-mono p-fg-mute" style={{ fontSize: 10.5, letterSpacing: '0.32em', marginBottom: 10 }}>
          MANOR MASTER SYSTEM
        </div>
        <h1 className="p-display" style={{ fontSize: 44, margin: '0 0 10px', letterSpacing: '0.005em' }}>
          Sebastian
        </h1>
        <p className="p-serif" style={{ fontSize: 16, fontStyle: 'italic', color: 'var(--fg-mute)', lineHeight: 1.5, maxWidth: 320, margin: '0 auto' }}>
          พ่อบ้านส่วนตัวสำหรับผู้รับเหมา —<br />
          เฝ้าระวังงานประมูลใหม่ วิเคราะห์คู่แข่ง<br />จัดเอกสารแทนท่าน
        </p>

        <div style={{ marginTop: 28, display: 'flex', justifyContent: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="p-chip p-chip-gold"><BellIcon />แจ้งเตือนงาน 06:00 ทุกวัน</span>
          <span className="p-chip p-chip-outline"><DocIcon />สรุปเอกสาร</span>
          <span className="p-chip p-chip-outline"><TrendIcon />วิเคราะห์คู่แข่ง</span>
        </div>
      </div>

      {/* Login actions */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <button
          className="p-btn p-btn-line"
          onClick={handleLogin}
          disabled={loading}
          style={{ width: '100%', height: 52, fontSize: 15.5 }}
        >
          <LineLogoIcon size={22} />
          {loading ? 'กำลังเชื่อมต่อกับ LINE…' : 'เข้าสู่ระบบด้วย LINE'}
        </button>

        <button
          onClick={() => setShowTiers(true)}
          style={{ background: 'transparent', border: 0, color: 'var(--fg-mute)', padding: '8px', fontSize: 13, textAlign: 'center', textDecoration: 'underline', textUnderlineOffset: 4, textDecorationColor: 'var(--accent-deep)', cursor: 'pointer' }}
        >
          ดูแพ็กเกจราคา ก่อนเข้าสู่ระบบ
        </button>

        <div className="p-mono p-fg-dim" style={{ fontSize: 11, textAlign: 'center', letterSpacing: '0.04em', marginTop: 4 }}>
          ทดลองใช้ฟรี 30 วัน · ไม่ต้องผูกบัตร
        </div>
      </div>

      {/* Bottom ornament */}
      <div style={{ display: 'flex', justifyContent: 'center', marginTop: 28 }}>
        <DividerOrnate />
      </div>
      <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.18em', textAlign: 'center', marginTop: 12 }}>
        EST. ANNO MMXXVI · BANGKOK
      </div>

      {showTiers && <TierModal onClose={() => setShowTiers(false)} />}
    </div>
  );
}
