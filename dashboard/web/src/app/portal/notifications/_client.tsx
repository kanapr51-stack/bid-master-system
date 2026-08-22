'use client';
/**
 * ขั้นตอนสุดท้ายของ onboarding — ขอ permission web push จริง หรือกด "ข้ามไปก่อน"
 * โค้ดขอ permission/subscribe เหมือน PushNotifyBadge.tsx (ไอคอนสถานะในหน้า world ที่ทำหน้าที่
 * เป็นตัวเตือนถ้าข้าม/ปฏิเสธตรงนี้) — spec: 2026-07-30-portal-onboarding-flow-design.md
 */
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { TopBar, Icons, ButlerNote } from '../_ui';
import type { PortalNotes } from '@/lib/portal-data';

const VAPID_PUBLIC = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? '';

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

type State = 'loading' | 'unsupported' | 'ios-install' | 'off' | 'on' | 'denied';

export function NotificationsClient({ notes }: { notes: PortalNotes }) {
  const router = useRouter();
  const [state, setState] = useState<State>('loading');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    (async () => {
      if (!('serviceWorker' in navigator) || !('PushManager' in window) || !VAPID_PUBLIC) {
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        const standalone = window.matchMedia('(display-mode: standalone)').matches
          || (navigator as unknown as { standalone?: boolean }).standalone === true;
        setState(isIOS && !standalone ? 'ios-install' : 'unsupported');
        return;
      }
      if (Notification.permission === 'denied') { setState('denied'); return; }
      const reg = await navigator.serviceWorker.register('/sw.js');
      const sub = await reg.pushManager.getSubscription();
      setState(sub ? 'on' : 'off');
    })().catch(() => setState('unsupported'));
  }, []);

  const goToBoard = useCallback(() => router.push('/portal/world'), [router]);

  const skip = useCallback(async () => {
    setBusy(true);
    try {
      await fetch('/api/portal/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...notes, notificationsPromptDismissedAt: new Date().toISOString() }),
      });
    } finally {
      setBusy(false);
      goToBoard();
    }
  }, [notes, goToBoard]);

  const enable = useCallback(async () => {
    setBusy(true); setMsg('');
    try {
      const perm = await Notification.requestPermission();
      if (perm !== 'granted') { setState(perm === 'denied' ? 'denied' : 'off'); return; }
      const reg = await navigator.serviceWorker.register('/sw.js');
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC) as BufferSource,
      });
      const json = sub.toJSON();
      const r = await fetch('/api/portal/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: sub.endpoint,
          p256dh: json.keys?.p256dh ?? '',
          auth: json.keys?.auth ?? '',
          user_agent: navigator.userAgent,
        }),
      });
      if (r.status === 403) {
        await sub.unsubscribe();
        setState('off'); setMsg('ฟีเจอร์นี้ยังเปิดทดลองเฉพาะบางบัญชี — กดข้ามไปก่อนได้ครับ');
        return;
      }
      if (!(await r.json()).ok) throw new Error('save failed');
      setState('on');
      goToBoard();
    } catch {
      setMsg('เปิดไม่สำเร็จ ลองใหม่อีกครั้ง หรือกด "ข้ามไปก่อน" แล้วเปิดทีหลังได้');
    } finally { setBusy(false); }
  }, [goToBoard]);

  if (state === 'loading') return null;

  return (
    <div className="p-enter">
      <TopBar title="เปิดการแจ้งเตือน" subtitle="ขั้นตอนสุดท้าย · Sebastian" />
      <div className="p-page p-page-topbar" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <ButlerNote>
          เปิดรับแจ้งเตือนบนเบราว์เซอร์เครื่องนี้ไว้ครับ Sebastian จะได้แจ้งงานประมูลใหม่ให้ทันทีที่เจอ
        </ButlerNote>

        <div className="p-card" style={{ padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent)', marginBottom: 8 }}>
            <Icons.Bell size={18} />
            <span className="p-display" style={{ fontSize: 16 }}>แจ้งเตือนผ่านเบราว์เซอร์</span>
          </div>

          {state === 'ios-install' && (
            <p className="p-fg-mute" style={{ fontSize: 13, lineHeight: 1.6 }}>
              iPhone/iPad: กดปุ่มแชร์ แล้วเลือก &quot;เพิ่มไปยังหน้าจอโฮม&quot; ก่อน
              จากนั้นเปิดจากไอคอนบนหน้าจอโฮมเพื่อเปิดรับแจ้งเตือน — กด &quot;ข้ามไปก่อน&quot; ได้ถ้ายังไม่สะดวก
            </p>
          )}
          {state === 'denied' && (
            <p className="p-fg-mute" style={{ fontSize: 13, lineHeight: 1.6 }}>
              เบราว์เซอร์นี้ถูกตั้งค่าบล็อกแจ้งเตือนไว้ — ไปที่ตั้งค่าเว็บไซต์ของเบราว์เซอร์แล้วอนุญาต
              จากนั้นรีเฟรชหน้านี้ หรือกด &quot;ข้ามไปก่อน&quot; แล้วเปิดทีหลังได้
            </p>
          )}
          {state === 'unsupported' && (
            <p className="p-fg-mute" style={{ fontSize: 13, lineHeight: 1.6 }}>
              เบราว์เซอร์นี้ยังไม่รองรับแจ้งเตือนแบบ push — กด &quot;ข้ามไปก่อน&quot; ได้เลยครับ
            </p>
          )}
          {state === 'on' && (
            <p className="p-fg-mute" style={{ fontSize: 13 }}>✅ เครื่องนี้เปิดรับแจ้งเตือนอยู่แล้ว</p>
          )}

          {state === 'off' && (
            <button className="p-btn p-btn-primary" onClick={enable} disabled={busy}
              style={{ width: '100%', height: 44, marginTop: 10 }}>
              {busy ? 'กำลังเปิด…' : 'เปิดการแจ้งเตือน'}
            </button>
          )}
          {msg && <p className="p-fg-dim" style={{ fontSize: 12.5, marginTop: 8 }}>{msg}</p>}
        </div>

        {state === 'on' ? (
          <button className="p-btn p-btn-primary" onClick={goToBoard} style={{ width: '100%', height: 44 }}>
            เข้าใช้งานบอร์ด
          </button>
        ) : (
          <button className="p-btn p-btn-ghost" onClick={skip} disabled={busy} style={{ width: '100%', height: 44 }}>
            ข้ามไปก่อน
          </button>
        )}
      </div>
    </div>
  );
}
