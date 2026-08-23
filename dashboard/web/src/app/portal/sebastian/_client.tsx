'use client';

import { useEffect, useMemo, useRef } from 'react';
import Link from 'next/link';
import { TopBar, Icons } from '../_ui';
import type { SebastianFeed, SebastianMessage } from '@/lib/portal-sebastian-feed';
import { dayKey, dayLabel, getTodayKey, getYesterdayKey } from '@/lib/portal-day-groups';

function fmtTime(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Bangkok' });
}

function MessageBubble({ msg }: { msg: SebastianMessage }) {
  return (
    <Link href={`/portal/job/${encodeURIComponent(msg.project_id)}`} prefetch={false} style={{ textDecoration: 'none', color: 'inherit' }}>
      <div className="p-chat-bubble">
        {msg.starred && (
          <div style={{ color: 'var(--accent)', fontSize: 12, marginBottom: 4 }}>★ ติดดาวไว้</div>
        )}
        <div style={{ fontSize: 13.5, lineHeight: 1.55, whiteSpace: 'pre-line' }}>{msg.message}</div>
        <div className="p-fg-dim" style={{ fontSize: 10.5, marginTop: 6 }}>{fmtTime(msg.sent_at)}</div>
      </div>
    </Link>
  );
}

export function SebastianClient({ data, engineDown }: { data: SebastianFeed | null; engineDown: boolean }) {
  const dayGroups = useMemo(() => {
    const m = new Map<string, SebastianMessage[]>();
    for (const msg of data?.messages ?? []) {
      const k = dayKey(msg.sent_at);
      const arr = m.get(k);
      if (arr) arr.push(msg); else m.set(k, [msg]);
    }
    return [...m.entries()];
  }, [data]);

  // เปิดหน้ามาต้องเห็นข้อความล่าสุด (ล่างสุด) ทันที — ไม่ใช่ต้องเลื่อนผ่านประวัติทั้งหมดก่อน
  // (ลำดับ oldest→newest ถูกแล้วตาม spec, แค่ขาด auto-scroll ตอน mount)
  const bottomRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [dayGroups]);

  if (!data) {
    return (
      <div className="p-enter">
        <TopBar title="Sebastian" subtitle="ประวัติการแจ้งเตือน" />
        <div className="p-page p-page-topbar">
          <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
              {engineDown ? 'ดึงข้อมูลไม่ได้ชั่วคราว — ลองใหม่อีกครั้งครับ' : 'ยังไม่มีข้อมูล'}
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

  return (
    <div className="p-enter">
      <TopBar title="Sebastian" subtitle="ประวัติการแจ้งเตือน" right={<Icons.Bot size={20} />} />
      <div className="p-page p-page-topbar">
        {data.messages.length === 0 ? (
          <div className="p-card" style={{ textAlign: 'center', padding: 28 }}>
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14 }}>
              ยังไม่มีการแจ้งเตือน — เมื่อ Sebastian พบงานที่ตรงกับท่าน จะทักมาที่นี่ครับ
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {(() => {
              const todayKey = getTodayKey();
              const yesterdayKey = getYesterdayKey();
              return dayGroups.map(([key, dayMsgs]) => (
                <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ marginTop: 8, textAlign: 'center' }}>
                    <span className="p-fg-dim" style={{ fontSize: 11.5 }}>{dayLabel(key, todayKey, yesterdayKey)}</span>
                  </div>
                  {dayMsgs.map(msg => <MessageBubble key={msg.project_id} msg={msg} />)}
                </div>
              ));
            })()}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}
