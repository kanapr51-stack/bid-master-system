'use client';
/**
 * Shared UI primitives for the Sebastian Customer Portal
 * Client Component — used across all portal pages
 */

import { type ReactNode } from 'react';

// ── Crest ─────────────────────────────────────────────────────────────────────

export function Crest({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size * 76 / 64} viewBox="0 0 64 76" fill="none" aria-label="Sebastian crest">
      <path d="M32 2 L58 14 L58 40 C58 54 46 66 32 74 C18 66 6 54 6 40 L6 14 Z" stroke="currentColor" strokeWidth="1.5" fill="none" />
      <path d="M32 2 L58 14 L58 40 C58 54 46 66 32 74 C18 66 6 54 6 40 L6 14 Z" fill="currentColor" fillOpacity="0.06" />
      <text x="32" y="48" textAnchor="middle" fontSize="28" fontFamily="var(--font-display, serif)" fontWeight="600" fill="currentColor" style={{ letterSpacing: '-0.02em' }}>S</text>
      <line x1="18" y1="30" x2="46" y2="30" stroke="currentColor" strokeWidth="0.75" opacity="0.5" />
      <circle cx="32" cy="24" r="3" fill="currentColor" fillOpacity="0.5" />
    </svg>
  );
}

// ── Diamond ───────────────────────────────────────────────────────────────────

export function Diamond({ size = 5, color = 'currentColor' }: { size?: number; color?: string }) {
  return <svg width={size * 2} height={size * 2} viewBox="0 0 10 10"><polygon points="5,1 9,5 5,9 1,5" fill={color} /></svg>;
}

// ── Icons ─────────────────────────────────────────────────────────────────────

type IconProps = { size?: number; sw?: number; style?: React.CSSProperties };

const I = (d: string, extra?: string) => ({ size = 18, sw = 1.5, style }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" style={style} dangerouslySetInnerHTML={{ __html: d + (extra || '') }} />
);

export const Icons = {
  Home: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" /></svg>,
  Bell: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>,
  Crown: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M2 4l4 8 6-4 6 4 4-8"/><rect x="2" y="18" width="20" height="2" rx="1"/><line x1="2" y1="12" x2="22" y2="12"/></svg>,
  Layers: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>,
  User: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>,
  Map: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>,
  Tag: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>,
  Clock: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>,
  Plus: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>,
  X: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>,
  Pin: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>,
  Check: ({ size = 18, sw = 2, style }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" style={style}><polyline points="20 6 9 17 4 12"/></svg>,
  Check2: ({ size = 18, sw = 2 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>,
  ChevronLeft: ({ size = 18, sw = 2 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>,
  ChevronRight: ({ size = 18, sw = 2 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>,
  ChevronDown: ({ size = 18, sw = 2, style }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" style={style}><polyline points="6 9 12 15 18 9"/></svg>,
  LogOut: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>,
  Edit: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>,
  Trash: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>,
  Compass: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>,
  Doc: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>,
  Shield: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  Flag: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>,
  Bot: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/><line x1="12" y1="3" x2="12" y2="7"/><circle cx="9" cy="16" r="1" fill="currentColor"/><circle cx="15" cy="16" r="1" fill="currentColor"/></svg>,
  Sparkles: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z"/><path d="M5 3l.5 1.5L7 5l-1.5.5L5 7l-.5-1.5L3 5l1.5-.5L5 3z"/><path d="M19 15l.5 1.5L21 17l-1.5.5L19 19l-.5-1.5L17 17l1.5-.5L19 15z"/></svg>,
  Coin: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="8"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>,
  Info: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>,
  Folder: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>,
  Star: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>,
  StarFilled: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>,
  Search: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>,
  TrendUp: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>,
  Upload: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>,
  Phone: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.6 1.1h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 8.69a16 16 0 0 0 6.29 6.29l.95-.95a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>,
  Mail: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>,
  Building: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/><path d="M3 9h6"/><path d="M3 15h6"/><path d="M15 8h1"/><path d="M15 12h1"/><path d="M15 16h1"/></svg>,
  FileText: ({ size = 18, sw = 1.5 }: IconProps) => <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>,
};

// ── TopBar ────────────────────────────────────────────────────────────────────

interface TopBarProps {
  title: string;
  subtitle?: string;
  left?: ReactNode;
  right?: ReactNode;
  onLeft?: () => void;
}

export function TopBar({ title, subtitle, left, right, onLeft }: TopBarProps) {
  return (
    <div className="p-topbar">
      {(left || onLeft) && (
        <button className="p-icon-btn" onClick={onLeft}>{left ?? <Icons.ChevronLeft size={20} />}</button>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="p-display" style={{ fontSize: 20, lineHeight: 1.2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</div>
        {subtitle && <div className="p-fg-dim p-mono" style={{ fontSize: 10.5, letterSpacing: '0.04em', marginTop: 1 }}>{subtitle}</div>}
      </div>
      {right && <div style={{ display: 'flex', gap: 4 }}>{right}</div>}
    </div>
  );
}

// ── ButlerNote ────────────────────────────────────────────────────────────────

export function ButlerNote({ children, tone = 'default' }: { children: ReactNode; tone?: 'gold' | 'default' }) {
  return (
    <div className="p-butler" style={{ borderLeftColor: tone === 'gold' ? 'var(--accent)' : 'var(--border)' }}>
      {children}
    </div>
  );
}

// ── Chip ──────────────────────────────────────────────────────────────────────

export function Chip({ children, tone = 'outline', icon, onRemove }: { children: ReactNode; tone?: 'gold' | 'emerald' | 'wine' | 'outline'; icon?: ReactNode; onRemove?: () => void }) {
  return (
    <span className={`p-chip p-chip-${tone}`}>
      {icon}
      {children}
      {onRemove && <button onClick={onRemove} style={{ background: 'none', border: 'none', padding: '0 0 0 2px', cursor: 'pointer', color: 'inherit', display: 'flex', alignItems: 'center', lineHeight: 1 }}><Icons.X size={10} /></button>}
    </span>
  );
}

// ── Toggle ────────────────────────────────────────────────────────────────────

export function Toggle({ value, onChange, label, hint }: { value: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <div className="p-toggle-wrap" style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, padding: '14px 0' }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 500 }}>{label}</div>
        {hint && <div className="p-fg-dim" style={{ fontSize: 12, marginTop: 2 }}>{hint}</div>}
      </div>
      <button className="p-toggle-track" data-on={String(value)} onClick={() => onChange(!value)}>
        <span className="p-toggle-thumb" />
      </button>
    </div>
  );
}

// ── Field ─────────────────────────────────────────────────────────────────────

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label className="p-label">{label}</label>
      {children}
      {hint && <div className="p-fg-dim p-serif" style={{ fontSize: 12, marginTop: 4, fontStyle: 'italic' }}>{hint}</div>}
    </div>
  );
}

// ── Modal ─────────────────────────────────────────────────────────────────────

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title?: string; children: ReactNode }) {
  if (!open) return null;
  return (
    <div className="p-scrim" onClick={onClose}>
      <div className="p-modal p-enter" onClick={e => e.stopPropagation()}>
        {title && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div className="p-display" style={{ fontSize: 20 }}>{title}</div>
            <button className="p-icon-btn" onClick={onClose}><Icons.X /></button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

// ── DividerOrnate ─────────────────────────────────────────────────────────────

export function DividerOrnate({ label }: { label?: string }) {
  if (label) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '20px 0 12px', color: 'var(--fg-dim)' }}>
        <div style={{ flex: 1, height: 1, background: 'var(--line)' }} />
        <span className="p-mono" style={{ fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--fg-dim)' }}>{label}</span>
        <div style={{ flex: 1, height: 1, background: 'var(--line)' }} />
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: 'var(--fg-dim)', width: '100%', maxWidth: 240 }}>
      <div style={{ flex: 1, height: 1, background: 'var(--line)' }} />
      <Diamond size={4} />
      <div style={{ flex: 1, height: 1, background: 'var(--line)' }} />
      <Diamond size={3} />
      <div style={{ flex: 1, height: 1, background: 'var(--line)' }} />
    </div>
  );
}
