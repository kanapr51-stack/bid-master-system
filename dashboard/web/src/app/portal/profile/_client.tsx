'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { TopBar, Chip, Icons, Crest, Toggle, Field, Modal, DividerOrnate, ButlerNote } from '../_ui';
import type { PortalProfile } from '@/lib/portal-data';

// ── Budget Range ──────────────────────────────────────────────────────────────

function BudgetRange({ min, max, onChange }: { min: number; max: number; onChange: (min: number, max: number) => void }) {
  const MIN = 0.1, MAX = 100;
  const pctMin = ((Math.min(min, MAX) - MIN) / (MAX - MIN)) * 100;
  const pctMax = ((Math.min(max, MAX) - MIN) / (MAX - MIN)) * 100;
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12, gap: 8 }}>
        <div><div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em' }}>MIN</div><div className="p-display p-fg-accent" style={{ fontSize: 22 }}>{min.toLocaleString()} ลบ.</div></div>
        <div className="p-fg-dim" style={{ fontSize: 12 }}>—</div>
        <div style={{ textAlign: 'right' }}><div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em' }}>MAX</div><div className="p-display p-fg-accent" style={{ fontSize: 22 }}>{max.toLocaleString()} ลบ.</div></div>
      </div>
      <div style={{ position: 'relative', height: 6, background: 'var(--border)', borderRadius: 3, marginBottom: 18 }}>
        <div style={{ position: 'absolute', height: '100%', left: `${pctMin}%`, right: `${100 - pctMax}%`, background: 'var(--accent)', borderRadius: 3 }} />
        <div style={{ position: 'absolute', top: '50%', transform: 'translate(-50%, -50%)', left: `${pctMin}%`, width: 14, height: 14, background: 'var(--accent)', borderRadius: '50%', border: '2px solid var(--bg)' }} />
        <div style={{ position: 'absolute', top: '50%', transform: 'translate(-50%, -50%)', left: `${pctMax}%`, width: 14, height: 14, background: 'var(--accent)', borderRadius: '50%', border: '2px solid var(--bg)' }} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, marginBottom: 4, letterSpacing: '0.06em' }}>MIN (ล้านบาท)</div>
          <input className="p-input" type="number" step="0.5" min="0.1" max={max - 0.1} value={min} onChange={e => onChange(Math.max(0.1, parseFloat(e.target.value) || 0), max)} />
        </div>
        <div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, marginBottom: 4, letterSpacing: '0.06em' }}>MAX (ล้านบาท)</div>
          <input className="p-input" type="number" step="0.5" min={min + 0.1} max="500" value={max} onChange={e => onChange(min, Math.max(min + 0.1, parseFloat(e.target.value) || 0))} />
        </div>
      </div>
    </div>
  );
}

// ── Time Picker ───────────────────────────────────────────────────────────────

function TimePicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const hours = ['05:00', '06:00', '07:00', '08:00', '09:00', '12:00', '18:00'];
  return (
    <div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
        {hours.map(h => (
          <button key={h} onClick={() => onChange(h)}
            className={value === h ? 'p-chip p-chip-gold' : 'p-chip p-chip-outline'}
            style={{ cursor: 'pointer', padding: '8px 14px', fontSize: 13, fontFamily: 'var(--font-mono)', border: '1px solid ' + (value === h ? 'var(--accent-deep)' : 'var(--border)') }}>
            {h}
          </button>
        ))}
      </div>
      <input className="p-input" type="time" value={value} onChange={e => onChange(e.target.value)} />
    </div>
  );
}

// ── Stat ──────────────────────────────────────────────────────────────────────

function Stat({ label, value, valueColor }: { label: string; value: string | number; valueColor?: string }) {
  return (
    <div>
      <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase' }}>{label}</div>
      <div className="p-display" style={{ fontSize: 18, marginTop: 2, color: valueColor || 'inherit' }}>{value}</div>
    </div>
  );
}

// ── Profile Client ────────────────────────────────────────────────────────────

interface Props {
  lineUserId: string;
  initialProfile: PortalProfile;
  classCount: number;
  registeredAt: string;
  tierId: string;
  daysLeft?: number;
  expiryLabel?: string;
}

export function ProfileClient({ lineUserId, initialProfile, classCount, registeredAt, tierId, daysLeft = 30, expiryLabel = '' }: Props) {
  const router = useRouter();
  const [profile, setProfile] = useState(initialProfile);
  const [showLogout, setShowLogout] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const update = (patch: Partial<PortalProfile>) => setProfile(p => ({ ...p, ...patch }));

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch('/api/portal/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          budgetMin: profile.budgetMin,
          budgetMax: profile.budgetMax,
          isSME: profile.isSME,
          isMIT: profile.isMIT,
          notifyTime: profile.notifyTime,
        }),
      });
      // Update display_name + phone/email via customer API
      await fetch(`/api/line/customer?lineUserId=${lineUserId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: profile.companyName, phone: profile.phone, email: profile.email }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = async () => {
    await fetch('/api/auth/line/logout', { method: 'POST' }).catch(() => {});
    router.push('/portal/login');
  };

  return (
    <div className="p-enter">
      <TopBar title="โปรไฟล์บริษัท" subtitle="Company Profile" />
      <div className="p-page p-page-topbar">
        {/* Crest header */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '16px 0 24px', textAlign: 'center' }}>
          <div style={{ marginBottom: 18 }}>
            <div style={{ width: 84, height: 84, borderRadius: 12, background: 'var(--surface)', border: '1px solid var(--accent-deep)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
              <Crest size={56} />
            </div>
          </div>
          <div className="p-display" style={{ fontSize: 22, lineHeight: 1.25, padding: '0 24px' }}>{profile.companyName || '(ยังไม่ระบุชื่อบริษัท)'}</div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 11, letterSpacing: '0.08em', marginTop: 8 }}>MEMBER · MMXXVI</div>
          <div style={{ display: 'flex', gap: 6, marginTop: 14, flexWrap: 'wrap', justifyContent: 'center' }}>
            {profile.isSME && <Chip tone="emerald" icon={<Icons.Shield size={11} />}>SME · แต้มต่อ 7.5%</Chip>}
            {profile.isMIT && <Chip tone="emerald" icon={<Icons.Flag size={11} />}>Made in Thailand</Chip>}
          </div>
        </div>

        <DividerOrnate label="ข้อมูลบริษัท" />

        <Field label="ชื่อบริษัท / ชื่อที่แสดง">
          <input className="p-input" value={profile.companyName} onChange={e => update({ companyName: e.target.value })} />
        </Field>
        <Field label="เบอร์โทรศัพท์">
          <input className="p-input" value={profile.phone} onChange={e => update({ phone: e.target.value })} placeholder="02-xxx-xxxx" inputMode="tel" />
        </Field>
        <Field label="อีเมล">
          <input className="p-input" value={profile.email} onChange={e => update({ email: e.target.value })} placeholder="info@company.co.th" inputMode="email" />
        </Field>

        <DividerOrnate label="ขอบเขตงาน" />

        <div style={{ marginBottom: 14 }}>
          <div className="p-label">ช่วงมูลค่างานที่รับ</div>
          <BudgetRange min={profile.budgetMin} max={profile.budgetMax} onChange={(min, max) => update({ budgetMin: min, budgetMax: max })} />
          <div className="p-serif" style={{ fontSize: 14, marginTop: 10, fontStyle: 'italic', color: 'var(--fg-mute)' }}>
            Sebastian จะแจ้งเตือนเฉพาะงานที่อยู่ในช่วง{' '}
            <span className="p-fg-accent" style={{ fontStyle: 'normal' }}>{profile.budgetMin.toLocaleString()} – {profile.budgetMax.toLocaleString()} ล้านบาท</span>
          </div>
        </div>

        <DividerOrnate label="คุณสมบัติพิเศษ" />

        <div className="p-card" style={{ padding: '0 16px' }}>
          <div style={{ borderBottom: '1px solid var(--line)' }}>
            <Toggle value={profile.isSME} onChange={v => update({ isSME: v })} label="บริษัทเป็น SME" hint="ได้แต้มต่อ 7.5% ในการประมูลงานภาครัฐ" />
          </div>
          <Toggle value={profile.isMIT} onChange={v => update({ isMIT: v })} label="สินค้า Made in Thailand" hint="ได้สิทธิ์พิเศษในงานประมูลที่กำหนด MIT" />
        </div>

        <DividerOrnate label="การแจ้งเตือน" />

        <Field label="เวลาแจ้งเตือนงานประจำวัน" hint="Sebastian จะส่งสรุปงานใหม่ใน LINE ทุกวันตามเวลานี้">
          <TimePicker value={profile.notifyTime} onChange={v => update({ notifyTime: v })} />
        </Field>

        {/* Save button */}
        <button className="p-btn p-btn-primary" onClick={handleSave} disabled={saving} style={{ width: '100%', height: 48, fontSize: 15, marginTop: 4, marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          {saved ? <><Icons.Check2 size={16} />บันทึกเสร็จแล้ว</> : saving ? 'กำลังบันทึก…' : <><Icons.Check size={16} />บันทึกการตั้งค่า</>}
        </button>

        {/* Account Status */}
        <DividerOrnate label="สถานะบัญชี" />
        <div className="p-card" style={{ marginBottom: 16, padding: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Stat label="แพ็กเกจ" value={tierId} />
            <Stat label="บริษัทที่ลงทะเบียน" value={classCount} />
            {registeredAt && <Stat label="สมัครเมื่อ" value={registeredAt} />}
            <div>
              <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em', textTransform: 'uppercase' }}>หมดอายุ</div>
              <div className="p-display" style={{ fontSize: 15, marginTop: 2, color: daysLeft <= 7 ? 'var(--wine-soft)' : 'var(--accent)' }}>
                {expiryLabel || '—'}
              </div>
              {expiryLabel && <div className="p-fg-dim" style={{ fontSize: 11 }}>เหลือ {daysLeft} วัน</div>}
            </div>
          </div>
          <div style={{ marginTop: 12, padding: '10px 12px', borderRadius: 8, background: 'var(--surface-2)', border: '1px solid var(--line)' }}>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.06em' }}>LINE USER ID</div>
            <div className="p-mono" style={{ fontSize: 11, marginTop: 2, wordBreak: 'break-all', color: 'var(--fg-mute)' }}>{lineUserId}</div>
          </div>
        </div>

        <button className="p-btn p-btn-ghost" onClick={() => setShowLogout(true)}
          style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, color: 'var(--wine-soft)' }}>
          <Icons.LogOut size={16} />ออกจากระบบ
        </button>

        <Modal open={showLogout} onClose={() => setShowLogout(false)} title="ออกจากระบบ?">
          <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14, marginBottom: 16 }}>
            ขอบพระคุณที่ใช้บริการครับท่าน Sebastian จะรอรับใช้ท่านเสมอ
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="p-btn p-btn-ghost" onClick={() => setShowLogout(false)} style={{ flex: 1 }}>ยกเลิก</button>
            <button className="p-btn" onClick={handleLogout} style={{ flex: 1, background: 'var(--wine)', borderColor: 'var(--wine)', color: 'white' }}>ออกจากระบบ</button>
          </div>
        </Modal>
      </div>
    </div>
  );
}
