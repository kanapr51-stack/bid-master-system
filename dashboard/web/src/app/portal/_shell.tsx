'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

// ── Icon primitives (subset of design icons) ─────────────────────────────────

function HomeIcon({ size = 20, active = false }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2 : 1.5} strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  );
}

function LayersIcon({ size = 20, active = false }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2 : 1.5} strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  );
}

function UserIcon({ size = 20, active = false }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2 : 1.5} strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function CrownIcon({ size = 20, active = false }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2 : 1.5} strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 4l4 8 6-4 6 4 4-8" />
      <rect x="2" y="18" width="20" height="2" rx="1" />
      <line x1="2" y1="12" x2="22" y2="12" />
    </svg>
  );
}

function ClockIcon({ size = 20, active = false }: { size?: number; active?: boolean }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2 : 1.5} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

// ── Nav items ─────────────────────────────────────────────────────────────────

const NAV_ITEMS = [
  { href: '/portal/world',    label: 'หน้าหลัก', Icon: HomeIcon },
  { href: '/portal/classes',  label: 'บริษัท',   Icon: LayersIcon },
  { href: '/portal/history',  label: 'ประวัติ',   Icon: ClockIcon },
  { href: '/portal/profile',  label: 'โปรไฟล์',  Icon: UserIcon },
  { href: '/portal/packages', label: 'แพ็กเกจ',  Icon: CrownIcon },
];

// ── Shell ─────────────────────────────────────────────────────────────────────

export function PortalShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLoginPage = pathname === '/portal/login';

  return (
    <div className="p-shell" style={{ minHeight: '100dvh' }}>
      {children}
      {!isLoginPage && (
        <nav className="p-bottom-nav">
          {NAV_ITEMS.map(({ href, label, Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link key={href} href={href} className={`p-nav-item${active ? ' active' : ''}`}>
                <Icon size={20} active={active} />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>
      )}
    </div>
  );
}
