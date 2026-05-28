'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { TopBar, Chip, Icons, Crest, Modal, DividerOrnate, ButlerNote, Field } from '../_ui';
import type { PortalProfile, BusinessClass } from '@/lib/portal-data';

// ── CompanyContactCard ────────────────────────────────────────────────────────

function CompanyContactCard({
  cls,
  onStatsClick,
}: {
  cls: BusinessClass;
  onStatsClick: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const phones = cls.phones ?? [];
  const emails = cls.emails ?? [];

  return (
    <div className="p-card" style={{ padding: 0, overflow: 'hidden', borderLeft: `3px solid ${cls.color || 'var(--accent)'}` }}>
      <div
        style={{ padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}
        onClick={() => setExpanded(v => !v)}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="p-display" style={{ fontSize: 16, lineHeight: 1.25 }}>{cls.companyName || cls.name}</div>
          {cls.businessTypes?.length ? (
            <div className="p-mono p-fg-dim" style={{ fontSize: 10.5, marginTop: 2, letterSpacing: '0.02em' }}>
              {cls.businessTypes.slice(0, 2).join(' · ')}{cls.businessTypes.length > 2 ? ` +${cls.businessTypes.length - 2}` : ''}
            </div>
          ) : null}
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
          <button
            className="p-btn p-btn-ghost"
            onClick={e => { e.stopPropagation(); onStatsClick(); }}
            style={{ fontSize: 11, padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <Icons.TrendUp size={12} />สถิติ
          </button>
          <Icons.ChevronDown
            size={14}
            style={{ transform: expanded ? 'none' : 'rotate(-90deg)', transition: 'transform 0.15s', color: 'var(--fg-dim)' }}
          />
        </div>
      </div>

      {expanded && (
        <div style={{ padding: '0 14px 14px', display: 'flex', flexDirection: 'column', gap: 10, borderTop: '1px solid var(--line)' }}>
          <div style={{ paddingTop: 10 }}>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 8 }}>เบอร์โทรติดต่อ</div>
            {phones.length > 0 ? phones.map((p, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <div style={{ color: 'var(--accent)', flexShrink: 0 }}><Icons.Phone size={13} /></div>
                <span style={{ fontSize: 13, fontFamily: 'var(--font-mono)' }}>{p}</span>
              </div>
            )) : (
              <div className="p-fg-dim" style={{ fontSize: 12, fontStyle: 'italic' }}>ยังไม่ได้เพิ่มเบอร์โทร</div>
            )}
          </div>
          <div>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 8 }}>อีเมล</div>
            {emails.length > 0 ? emails.map((e, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <div style={{ color: 'var(--accent)', flexShrink: 0 }}><Icons.Mail size={13} /></div>
                <span style={{ fontSize: 13 }}>{e}</span>
              </div>
            )) : (
              <div className="p-fg-dim" style={{ fontSize: 12, fontStyle: 'italic' }}>ยังไม่ได้เพิ่มอีเมล</div>
            )}
          </div>
          {(cls.isSME || cls.isMIT) && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {cls.isSME && <Chip tone="emerald" icon={<Icons.Shield size={11} />}>SME +7.5%</Chip>}
              {cls.isMIT && <Chip tone="emerald" icon={<Icons.Flag size={11} />}>MIT</Chip>}
            </div>
          )}
        </div>
      )}
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
  classes: BusinessClass[];
  classCount: number;
  registeredAt: string;
  tierId: string;
  daysLeft?: number;
  expiryLabel?: string;
}

export function ProfileClient({
  lineUserId,
  initialProfile,
  classes,
  classCount,
  registeredAt,
  tierId,
  daysLeft = 30,
  expiryLabel = '',
}: Props) {
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
          userName: profile.userName,
          userGmail: profile.userGmail,
          userPhone: profile.userPhone,
          userLineId: profile.userLineId,
        }),
      });
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
      <TopBar title="โปรไฟล์" subtitle="Profile · Sebastian" />
      <div className="p-page p-page-topbar">

        {/* Crest header */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '16px 0 22px', textAlign: 'center' }}>
          <div style={{ marginBottom: 16 }}>
            <div style={{ width: 80, height: 80, borderRadius: 12, background: 'var(--surface)', border: '1px solid var(--accent-deep)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)' }}>
              <Crest size={52} />
            </div>
          </div>
          <div className="p-display" style={{ fontSize: 22, lineHeight: 1.25, padding: '0 24px' }}>
            {profile.userName || profile.companyName || '(ยังไม่ระบุชื่อ)'}
          </div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 11, letterSpacing: '0.08em', marginTop: 6 }}>MEMBER · MMXXVI</div>
        </div>

        {/* Personal Info */}
        <DividerOrnate label="ข้อมูลส่วนตัว" />
        <ButlerNote>ข้อมูลนี้ใช้เพื่อการแจ้งเตือนและการติดต่อกลับจาก Sebastian ครับท่าน</ButlerNote>

        <Field label="ชื่อ-นามสกุล">
          <input className="p-input" value={profile.userName ?? ''} onChange={e => update({ userName: e.target.value })} placeholder="ชื่อ-นามสกุลของท่าน" />
        </Field>
        <Field label="Gmail">
          <input className="p-input" value={profile.userGmail ?? ''} onChange={e => update({ userGmail: e.target.value })} placeholder="your.email@gmail.com" inputMode="email" />
        </Field>
        <Field label="เบอร์โทรส่วนตัว">
          <input className="p-input" value={profile.userPhone ?? ''} onChange={e => update({ userPhone: e.target.value })} placeholder="08x-xxx-xxxx" inputMode="tel" />
        </Field>
        <Field label="LINE ID">
          <input className="p-input" value={profile.userLineId ?? ''} onChange={e => update({ userLineId: e.target.value })} placeholder="LINE ID ของท่าน" />
        </Field>

        {/* Save personal info */}
        <button
          className="p-btn p-btn-primary"
          onClick={handleSave}
          disabled={saving}
          style={{ width: '100%', height: 44, fontSize: 14, marginTop: 4, marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
        >
          {saved ? <><Icons.Check2 size={16} />บันทึกเสร็จแล้ว</> : saving ? 'กำลังบันทึก…' : <><Icons.Check size={16} />บันทึกข้อมูลส่วนตัว</>}
        </button>

        {/* Per-company contacts */}
        {classes.length > 0 && (
          <>
            <DividerOrnate label="ข้อมูลติดต่อบริษัท" />
            <ButlerNote>กดที่บริษัทเพื่อดูหรือแก้ไขข้อมูลติดต่อ · กด "สถิติ" เพื่อดูประวัติการประมูล</ButlerNote>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
              {classes.map(cls => (
                <CompanyContactCard
                  key={cls.id}
                  cls={cls}
                  onStatsClick={() => router.push(`/portal/company-stats?classId=${cls.id}`)}
                />
              ))}
            </div>
          </>
        )}

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

        <button
          className="p-btn p-btn-ghost"
          onClick={() => setShowLogout(true)}
          style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, color: 'var(--wine-soft)' }}
        >
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
