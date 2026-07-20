'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { TopBar, Chip, Icons, ButlerNote, Toggle } from '../_ui';
import { DEFAULT_KEYWORDS_BY_CLASS, type PortalNotes, type BusinessClass } from '@/lib/portal-data';

// N+199: ตั้งค่าแบน — เก็บเป็น hidden class เดียวใน notes.classes (engine อ่านรูปเดิม ไม่ต้องแก้ matching)
function toClasses(keywords: string[], budgetMin: number, budgetMax: number): BusinessClass[] {
  if (keywords.length === 0 && !budgetMin && !budgetMax) return []; // ว่างหมด = เห็นทั้งจังหวัด
  return [{
    id: 'settings',
    name: 'ตั้งค่า',
    color: '#B8893A',
    geo: { mode: 'province', provinces: [], districts: [], tambons: [], gps: null, radiusKm: 30 },
    keywords,
    defaultKeywords: [],
    ...(budgetMin > 0 ? { budgetMinBaht: budgetMin } : {}),
    ...(budgetMax > 0 ? { budgetMaxBaht: budgetMax } : {}),
  }];
}

export function SettingsClient({ provinces, initialKeywords, initialBudgetMin, initialBudgetMax, initialIsSME, initialIsMIT, initialNotifyTime, initialMorningTime, notes }: {
  provinces: string[];
  initialKeywords: string[];
  initialBudgetMin: number;
  initialBudgetMax: number;
  initialIsSME: boolean;
  initialIsMIT: boolean;
  initialNotifyTime: string;
  initialMorningTime: string;
  notes: PortalNotes;
}) {
  const router = useRouter();
  const [keywords, setKeywords] = useState<string[]>(initialKeywords);
  const [kwInput, setKwInput] = useState('');
  const [budgetMin, setBudgetMin] = useState(initialBudgetMin);
  const [budgetMax, setBudgetMax] = useState(initialBudgetMax);
  const [isSME, setIsSME] = useState(initialIsSME);
  const [isMIT, setIsMIT] = useState(initialIsMIT);
  const [notifyTime, setNotifyTime] = useState(initialNotifyTime);
  const [morningTime, setMorningTime] = useState(initialMorningTime);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  const addKeyword = () => {
    const k = kwInput.trim();
    if (!k) return;
    if (!keywords.includes(k)) setKeywords([...keywords, k]);
    setKwInput('');
  };

  // N+201.1: preset ต่อหมวด (ชุดเดิมจากระบบบริษัท) — กดหมวด = เพิ่มคำทั้งชุด / กดซ้ำ = เอาชุดนั้นออก
  const presetSelected = (cat: string) =>
    (DEFAULT_KEYWORDS_BY_CLASS[cat] || []).some(k => keywords.includes(k));
  const togglePreset = (cat: string) => {
    const preset = DEFAULT_KEYWORDS_BY_CLASS[cat] || [];
    if (presetSelected(cat)) setKeywords(keywords.filter(k => !preset.includes(k)));
    else setKeywords([...new Set([...keywords, ...preset])]);
  };

  const save = async () => {
    setSaving(true); setError(''); setSaved(false);
    try {
      const body: PortalNotes = {
        ...notes,
        classes: toClasses(keywords, budgetMin, budgetMax),
        isSME, isMIT, notifyTime,
        morningNotifyTime: morningTime,
      };
      const r = await fetch('/api/portal/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error('save failed');
      setSaved(true);
      setTimeout(() => setSaved(false), 2200);
    } catch {
      setError('บันทึกไม่สำเร็จ — ลองใหม่อีกครั้งครับ');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-enter">
      <TopBar title="ตั้งค่า" subtitle="พื้นที่ · คำค้น · ช่วงงบ" onLeft={() => router.push('/portal/world')} />
      <div className="p-page p-page-topbar" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* 📍 พื้นที่ครอบคลุม — subscription จริง (read-only) */}
        <div className="p-card" style={{ padding: 16 }}>
          <div className="p-smallcaps p-fg-mute" style={{ marginBottom: 10 }}>📍 พื้นที่ครอบคลุม</div>
          {provinces.length > 0 ? (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {provinces.map(p => <Chip key={p} tone="gold" icon={<Icons.Pin size={10} />}>จ.{p}</Chip>)}
            </div>
          ) : (
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 13 }}>ยังไม่ได้กำหนดพื้นที่</div>
          )}
          <div className="p-fg-dim" style={{ fontSize: 11.5, marginTop: 10, lineHeight: 1.5 }}>
            พื้นที่นี้ใช้ทั้งแจ้งเตือน LINE และงานบนบอร์ด — ต้องการเปลี่ยนพื้นที่ แจ้ง Sebastian ได้เลยครับ
          </div>
        </div>

        {/* 🏷️ คำค้น */}
        <div className="p-card" style={{ padding: 16 }}>
          <div className="p-smallcaps p-fg-mute" style={{ marginBottom: 10 }}>🏷️ คำค้น</div>
          {keywords.length > 0 ? (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
              {keywords.map(k => (
                <button key={k} onClick={() => setKeywords(keywords.filter(x => x !== k))}
                  className="p-chip p-chip-gold" style={{ cursor: 'pointer', fontFamily: 'inherit' }}
                  title="กดเพื่อลบคำนี้">
                  {k} ✕
                </button>
              ))}
            </div>
          ) : (
            <ButlerNote>ยังไม่ตั้งคำค้น = จะยังไม่มีงานขึ้นให้เลย — ติ๊กเลือกจากหมวดด้านล่าง หรือพิมพ์เอง เช่น &quot;ถนน&quot; &quot;อาคาร&quot; เพื่อเริ่มเห็นงานที่ตรงกับท่าน</ButlerNote>
          )}
          <div style={{ marginTop: keywords.length > 0 ? 0 : 12 }}>
            <div className="p-fg-mute" style={{ fontSize: 12, marginBottom: 6 }}>เพิ่มเร็วจากหมวดสำเร็จรูป (กดเลือก · กดซ้ำเอาออก):</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
              {Object.keys(DEFAULT_KEYWORDS_BY_CLASS).map(cat => {
                const on = presetSelected(cat);
                return (
                  <button key={cat} onClick={() => togglePreset(cat)}
                    className={`p-chip ${on ? 'p-chip-gold' : 'p-chip-outline'}`}
                    style={{ cursor: 'pointer', fontFamily: 'inherit' }} aria-pressed={on}>
                    {on && '✓ '}{cat}
                  </button>
                );
              })}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input className="p-input" value={kwInput} onChange={e => setKwInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') addKeyword(); }}
              placeholder="หรือพิมพ์คำค้นเอง เช่น ถนน" style={{ flex: 1 }} />
            <button className="p-btn p-btn-ghost" onClick={addKeyword} style={{ height: 40, padding: '0 16px' }}>เพิ่ม</button>
          </div>
          {keywords.length > 0 && (
            <div className="p-fg-dim" style={{ fontSize: 11.5, marginTop: 10 }}>กดที่คำเพื่อลบ — ลบหมด = จะไม่มีงานขึ้นให้จนกว่าจะเพิ่มคำใหม่</div>
          )}
        </div>

        {/* 💰 ช่วงงบ */}
        <div className="p-card" style={{ padding: 16 }}>
          <div className="p-smallcaps p-fg-mute" style={{ marginBottom: 10 }}>💰 ช่วงราคากลางที่สนใจ</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <div className="p-fg-mute" style={{ fontSize: 12, marginBottom: 4 }}>งบต่ำสุด (บาท) — 0 = ไม่จำกัด</div>
              <input className="p-input" type="number" step="100000" min="0" value={budgetMin || ''}
                onChange={e => setBudgetMin(parseInt(e.target.value) || 0)} placeholder="ไม่จำกัด" style={{ width: '100%' }} />
              {budgetMin > 0 && <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 4 }}>= {(budgetMin / 1000000).toFixed(2)} ล้านบาท</div>}
            </div>
            <div>
              <div className="p-fg-mute" style={{ fontSize: 12, marginBottom: 4 }}>งบสูงสุด (บาท) — 0 = ไม่จำกัด</div>
              <input className="p-input" type="number" step="1000000" min="0" value={budgetMax || ''}
                onChange={e => setBudgetMax(parseInt(e.target.value) || 0)} placeholder="ไม่จำกัด" style={{ width: '100%' }} />
              {budgetMax > 0 && <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 4 }}>= {(budgetMax / 1000000).toFixed(2)} ล้านบาท</div>}
            </div>
          </div>
        </div>

        {/* 🔔 คุณสมบัติบริษัท & การแจ้งเตือน (ย้ายจากหน้าโปรไฟล์/บริษัทเดิม — N+199.1) */}
        <div className="p-card" style={{ padding: '0 16px' }}>
          <div className="p-smallcaps p-fg-mute" style={{ padding: '14px 0 4px' }}>🔔 คุณสมบัติบริษัท & การแจ้งเตือน</div>
          <div style={{ borderBottom: '1px solid var(--line)' }}>
            <Toggle value={isSME} onChange={setIsSME} label="บริษัทเป็น SME" hint="แสดงงานที่กำหนด SME ได้ (แต้มต่อ +7.5%)" />
          </div>
          <div style={{ borderBottom: '1px solid var(--line)' }}>
            <Toggle value={isMIT} onChange={setIsMIT} label="สินค้า Made in Thailand" hint="แสดงงานที่กำหนด MIT" />
          </div>
          <div style={{ padding: '12px 0', borderBottom: '1px solid var(--line)' }}>
            <div className="p-fg-mute" style={{ fontSize: 12, marginBottom: 4 }}>🌅 เวลาแจ้งเตือนตอนเช้า</div>
            <input className="p-input" type="time" value={morningTime}
              onChange={e => setMorningTime(e.target.value)} style={{ width: '100%' }} />
            <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 4 }}>งานที่ถึงกำหนดยื่นซองวันนี้ + แผนงานที่จดไว้สำหรับวันนี้</div>
          </div>
          <div style={{ padding: '12px 0 14px' }}>
            <div className="p-fg-mute" style={{ fontSize: 12, marginBottom: 4 }}>🌙 เวลาสรุปประจำวัน</div>
            <input className="p-input" type="time" value={notifyTime}
              onChange={e => setNotifyTime(e.target.value)} style={{ width: '100%' }} />
            <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 4 }}>สรุปงานที่ส่งวันนี้ + งานเปิดยื่นซองพรุ่งนี้</div>
          </div>
        </div>

        {error && <div className="p-fg-mute" style={{ fontSize: 12.5, color: 'var(--wine, #a33)' }}>{error}</div>}
        <button className="p-btn p-btn-primary" onClick={save} disabled={saving}
          style={{ width: '100%', height: 48, fontSize: 15, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          {saved ? <><Icons.Check size={16} />บันทึกเสร็จแล้ว</> : saving ? 'กำลังบันทึก…' : <><Icons.Check size={16} />บันทึกการตั้งค่า</>}
        </button>
      </div>
    </div>
  );
}
