import type { Metadata } from 'next';
import { Cormorant_Garamond, IBM_Plex_Mono } from 'next/font/google';
import './portal.css';
import { PortalShell } from './_shell';

const cormorant = Cormorant_Garamond({
  variable: '--font-cormorant',
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  style: ['normal', 'italic'],
});

const plexMono = IBM_Plex_Mono({
  variable: '--font-plex-mono',
  subsets: ['latin'],
  weight: ['300', '400', '500', '600'],
});

export const metadata: Metadata = {
  title: 'Sebastian · Bid Master System',
  description: 'พ่อบ้านส่วนตัวสำหรับผู้รับเหมา — เฝ้าระวังงานประมูลใหม่ วิเคราะห์คู่แข่ง',
};

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      data-portal
      data-theme="dark"
      className={`${cormorant.variable} ${plexMono.variable}`}
      style={{
        // Override font variables to use loaded fonts
        ['--font-display' as string]: `var(--font-cormorant), 'Sarabun', Georgia, serif`,
        ['--font-mono' as string]: `var(--font-plex-mono), 'Courier New', monospace`,
      }}
    >
      <PortalShell>{children}</PortalShell>
    </div>
  );
}
