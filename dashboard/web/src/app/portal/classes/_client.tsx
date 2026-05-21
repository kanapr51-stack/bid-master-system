'use client';

import { useState, useMemo, useRef, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { TopBar, Chip, Icons, Crest, Toggle, Field, Modal, ButlerNote, Diamond } from '../_ui';
import type { BusinessClass, CompanyFile } from '@/lib/portal-data';
import { THAI_PROVINCES, DEFAULT_KEYWORDS_BY_CLASS, CLASS_SUGGESTIONS, distanceKm } from '@/lib/portal-data';
import THAI_GEO_DATA from '@/app/portal/thai-geo-data';

const MapPreview = dynamic(() => import('./_map-preview').then(m => m.MapPreview), { ssr: false });

const THAI_GEO = THAI_GEO_DATA;

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseGoogleMapsUrl(url: string): { lat: number; lng: number } | null {
  if (!url || typeof url !== 'string') return null;
  const u = url.trim();
  const plain = u.match(/^(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)$/);
  if (plain) return { lat: parseFloat(plain[1]), lng: parseFloat(plain[2]) };
  const atMatch = u.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/);
  if (atMatch) return { lat: parseFloat(atMatch[1]), lng: parseFloat(atMatch[2]) };
  const qMatch = u.match(/[?&](?:q|ll|query|destination)=(-?\d+\.\d+),(-?\d+\.\d+)/);
  if (qMatch) return { lat: parseFloat(qMatch[1]), lng: parseFloat(qMatch[2]) };
  const placeMatch = u.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
  if (placeMatch) return { lat: parseFloat(placeMatch[1]), lng: parseFloat(placeMatch[2]) };
  return null;
}

function isShortGoogleMapsUrl(url: string) {
  return /(?:goo\.gl\/maps|maps\.app\.goo\.gl|g\.co\/kgs)/i.test(url);
}

function extractPlaceName(url: string) {
  const m = url.match(/\/place\/([^/@]+)/);
  if (!m) return '';
  try { return decodeURIComponent(m[1].replace(/\+/g, ' ')); } catch { return ''; }
}

const CLASS_COLORS = ['#C8A86A', '#8B2A36', '#4A7C59', '#5B5448'];

// ── GoogleMapsPicker ──────────────────────────────────────────────────────────

function GoogleMapsPicker({ current, onPick }: {
  current: { lat: number; lng: number; label: string } | null;
  onPick: (lat: number, lng: number, label: string) => void;
}) {
  const [link, setLink] = useState('');
  const [status, setStatus] = useState<null | 'ok' | 'short' | 'invalid'>(null);

  const tryParse = (raw: string) => {
    setLink(raw);
    if (!raw.trim()) { setStatus(null); return; }
    const coords = parseGoogleMapsUrl(raw);
    if (coords) {
      onPick(coords.lat, coords.lng, extractPlaceName(raw));
      setStatus('ok');
      return;
    }
    if (isShortGoogleMapsUrl(raw)) { setStatus('short'); return; }
    setStatus('invalid');
  };

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) tryParse(text);
    } catch { /* ignore */ }
  };

  return (
    <div style={{ padding: 12, borderRadius: 10, background: 'var(--gold-glow)', border: '1px solid var(--accent-deep)', marginBottom: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <div style={{ color: 'var(--accent)' }}><Icons.Map size={14} /></div>
        <div className="p-mono" style={{ fontSize: 10.5, letterSpacing: '0.08em', color: 'var(--accent)', fontWeight: 600 }}>วาง Google Maps Link</div>
        <div style={{ flex: 1 }} />
        <button onClick={handlePaste} className="p-mono" style={{ background: 'transparent', border: '1px solid var(--accent-deep)', color: 'var(--accent)', padding: '3px 9px', borderRadius: 6, fontSize: 10.5, letterSpacing: '0.04em', cursor: 'pointer' }}>
          วางจาก clipboard
        </button>
      </div>
      <input className="p-input" value={link} onChange={e => tryParse(e.target.value)} placeholder="https://maps.google.com/... หรือ 13.7563, 100.5018" style={{ fontSize: 13 }} />
      {status === 'ok' && (
        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icons.Check size={12} />
          <span className="p-mono" style={{ fontSize: 11, letterSpacing: '0.04em', color: '#88B89B' }}>
            ดึงพิกัดได้แล้ว: {current?.lat?.toFixed(4)}°N · {current?.lng?.toFixed(4)}°E
          </span>
        </div>
      )}
      {status === 'short' && (
        <div style={{ marginTop: 8, display: 'flex', alignItems: 'flex-start', gap: 6, color: 'var(--wine-soft)' }}>
          <Icons.Info size={12} />
          <span className="p-serif" style={{ fontSize: 12, fontStyle: 'italic', lineHeight: 1.4 }}>
            ลิงก์แบบสั้น (goo.gl) ไม่มีพิกัดในตัว กรุณาเปิดลิงก์ใน Google Maps แล้วคัดลอกลิงก์เต็ม หรือพิกัด lat, lng โดยตรง
          </span>
        </div>
      )}
      {status === 'invalid' && (
        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6, color: 'var(--fg-dim)' }}>
          <Icons.Info size={12} />
          <span className="p-mono" style={{ fontSize: 10.5, letterSpacing: '0.04em' }}>ไม่พบพิกัดในลิงก์นี้</span>
        </div>
      )}
      {status === null && (
        <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 6, fontStyle: 'italic', fontFamily: 'var(--font-serif)', lineHeight: 1.4 }}>
          วิธีหา: เปิด Google Maps → ค้นหาโรงงาน → คัดลอก URL จาก address bar
        </div>
      )}
    </div>
  );
}

// ── DistrictRow ───────────────────────────────────────────────────────────────

interface DistrictData { name: string; lat: number; lng: number; tambons: { name: string; lat: number; lng: number }[]; }

function DistrictRow({ district, dKey, picked, partial, tickedTambons, inRadiusDistrict, distance, pickedT, inRadiusT, hasRadius, gps, onToggleDistrict, onToggleTambon }: {
  district: DistrictData;
  dKey: string;
  picked: boolean;
  partial: boolean;
  tickedTambons: number;
  inRadiusDistrict: boolean;
  distance: number | null;
  pickedT: Set<string>;
  inRadiusT: Set<string>;
  hasRadius: boolean;
  gps: { lat: number; lng: number } | null;
  onToggleDistrict: () => void;
  onToggleTambon: (tKey: string) => void;
}) {
  const [openTambons, setOpenTambons] = useState(false);

  return (
    <div style={{ borderRadius: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', background: picked ? 'var(--gold-glow)' : 'transparent', borderRadius: 8 }}>
        <button onClick={onToggleDistrict} style={{ width: 18, height: 18, padding: 0, borderRadius: 4, border: `1.5px solid ${picked ? 'var(--accent)' : 'var(--border)'}`, background: picked ? 'var(--accent)' : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, cursor: 'pointer' }}>
          {picked && !partial && <Icons.Check size={11} />}
          {partial && <div style={{ width: 8, height: 2, background: 'var(--ink-deep)' }} />}
        </button>
        <button onClick={() => setOpenTambons(v => !v)} style={{ flex: 1, minWidth: 0, border: 0, background: 'transparent', textAlign: 'left', color: 'inherit', display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <span style={{ fontSize: 13.5, fontWeight: picked ? 500 : 400 }}>อ. {district.name}</span>
          {inRadiusDistrict && hasRadius && (
            <Chip tone="emerald" icon={<Icons.Compass size={10} />}>ในรัศมี{distance ? ` ${Math.round(distance)} กม.` : ''}</Chip>
          )}
          <span className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.04em', marginLeft: 'auto' }}>
            {tickedTambons}/{district.tambons.length}
          </span>
          <Icons.ChevronDown size={12} style={{ transform: openTambons ? 'none' : 'rotate(-90deg)', transition: 'transform 0.15s', color: 'var(--fg-dim)' }} />
        </button>
      </div>
      {openTambons && (
        <div style={{ padding: '6px 8px 8px 38px', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {district.tambons.map(t => {
            const tKey = `${dKey}::${t.name}`;
            const tPicked = pickedT.has(tKey);
            const tInRadius = inRadiusT.has(tKey);
            const tDist = hasRadius && gps ? distanceKm(gps.lat, gps.lng, t.lat, t.lng) : null;
            return (
              <button key={tKey} onClick={() => onToggleTambon(tKey)}
                className={tPicked ? 'p-chip p-chip-gold' : 'p-chip p-chip-outline'}
                style={{ cursor: 'pointer', border: tPicked ? '1px solid var(--accent-deep)' : '1px solid var(--border)', position: 'relative' }}>
                {tPicked && <Icons.Check size={10} />}
                <span>ต. {t.name}</span>
                {tInRadius && hasRadius && !tPicked && (
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--emerald)', marginLeft: 2 }} />
                )}
                {tDist != null && tPicked && (
                  <span className="p-mono" style={{ fontSize: 9, opacity: 0.7, marginLeft: 2 }}>{Math.round(tDist)} กม.</span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── ProvinceDistrictGroup ─────────────────────────────────────────────────────

function ProvinceDistrictGroup({ province, districts, pickedD, pickedT, inRadiusD, inRadiusT, hasRadius, radiusKm, gps, onToggleDistrict, onToggleTambon, onTickAll, onClearAll }: {
  province: string;
  districts: DistrictData[];
  pickedD: Set<string>;
  pickedT: Set<string>;
  inRadiusD: Set<string>;
  inRadiusT: Set<string>;
  hasRadius: boolean;
  radiusKm: number;
  gps: { lat: number; lng: number } | null;
  onToggleDistrict: (dKey: string, tambonKeys: string[]) => void;
  onToggleTambon: (tKey: string, dKey: string, allTambonKeys: string[]) => void;
  onTickAll: () => void;
  onClearAll: () => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const provincePickedTambons = districts.reduce((acc, d) =>
    acc + d.tambons.filter(t => pickedT.has(`${province}::${d.name}::${t.name}`)).length, 0);
  const provinceTotalTambons = districts.reduce((acc, d) => acc + d.tambons.length, 0);

  return (
    <div style={{ borderRadius: 10, border: '1px solid var(--line)', overflow: 'hidden' }}>
      <div style={{ padding: '10px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--surface-2)', cursor: 'pointer' }} onClick={() => setExpanded(v => !v)}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Icons.ChevronDown size={14} style={{ transform: expanded ? 'none' : 'rotate(-90deg)', transition: 'transform 0.15s', color: 'var(--fg-mute)' }} />
          <span style={{ fontSize: 14, fontWeight: 500 }}>{province}</span>
          <span className="p-mono p-fg-dim" style={{ fontSize: 10.5, letterSpacing: '0.04em' }}>
            {provincePickedTambons}/{provinceTotalTambons} ตำบล
          </span>
        </div>
        <div style={{ display: 'flex', gap: 6 }} onClick={e => e.stopPropagation()}>
          <button onClick={onTickAll} className="p-mono" style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--fg-mute)', padding: '2px 8px', borderRadius: 6, fontSize: 10, cursor: 'pointer', letterSpacing: '0.04em' }}>ทั้งหมด</button>
          <button onClick={onClearAll} className="p-mono" style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--fg-mute)', padding: '2px 8px', borderRadius: 6, fontSize: 10, cursor: 'pointer', letterSpacing: '0.04em' }}>ล้าง</button>
        </div>
      </div>
      {expanded && (
        <div style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {districts.map(d => {
            const dKey = `${province}::${d.name}`;
            const dTambonKeys = d.tambons.map(t => `${dKey}::${t.name}`);
            const dPicked = pickedD.has(dKey);
            const tickedTambons = dTambonKeys.filter(k => pickedT.has(k)).length;
            const partial = tickedTambons > 0 && tickedTambons < d.tambons.length;
            const inRad = inRadiusD.has(dKey);
            const dist = hasRadius && gps ? distanceKm(gps.lat, gps.lng, d.lat, d.lng) : null;
            return (
              <DistrictRow
                key={dKey}
                district={d}
                dKey={dKey}
                picked={dPicked}
                partial={partial}
                tickedTambons={tickedTambons}
                inRadiusDistrict={inRad}
                distance={dist}
                pickedT={pickedT}
                inRadiusT={inRadiusT}
                hasRadius={hasRadius}
                gps={gps}
                onToggleDistrict={() => onToggleDistrict(dKey, dTambonKeys)}
                onToggleTambon={(tKey) => onToggleTambon(tKey, dKey, dTambonKeys)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── DistrictTambonPicker ──────────────────────────────────────────────────────

function DistrictTambonPicker({ cls, onChange }: { cls: BusinessClass; onChange: (patch: Partial<BusinessClass>) => void }) {
  const { geo } = cls;
  const hasRadius = !!(geo.gps && geo.radiusKm > 0);

  const inRadius = useMemo(() => {
    if (!hasRadius || !geo.gps) return { districts: new Set<string>(), tambons: new Set<string>() };
    const dSet = new Set<string>();
    const tSet = new Set<string>();
    for (const [prov, districts] of Object.entries(THAI_GEO)) {
      for (const d of districts as DistrictData[]) {
        const dKey = `${prov}::${d.name}`;
        if (distanceKm(geo.gps!.lat, geo.gps!.lng, d.lat, d.lng) <= geo.radiusKm) dSet.add(dKey);
        for (const t of d.tambons) {
          if (distanceKm(geo.gps!.lat, geo.gps!.lng, t.lat, t.lng) <= geo.radiusKm) tSet.add(`${dKey}::${t.name}`);
        }
      }
    }
    return { districts: dSet, tambons: tSet };
  }, [hasRadius, geo.gps?.lat, geo.gps?.lng, geo.radiusKm]);

  const candidateProvinces = useMemo(() => {
    const s = new Set(geo.provinces);
    inRadius.tambons.forEach(k => s.add(k.split('::')[0]));
    inRadius.districts.forEach(k => s.add(k.split('::')[0]));
    return Array.from(s).filter(p => (THAI_GEO as Record<string, unknown>)[p]);
  }, [geo.provinces, inRadius]);

  const radiusSignature = `${geo.gps?.lat || 0}|${geo.gps?.lng || 0}|${geo.radiusKm || 0}`;
  const lastSig = useRef('');
  useEffect(() => {
    if (!hasRadius) return;
    if (lastSig.current === radiusSignature) return;
    lastSig.current = radiusSignature;
    const newDistricts = new Set([...geo.districts, ...inRadius.districts]);
    const newTambons = new Set([...geo.tambons, ...inRadius.tambons]);
    onChange({ geo: { ...geo, districts: Array.from(newDistricts), tambons: Array.from(newTambons) } });
  }, [radiusSignature]);

  const pickedD = new Set(geo.districts);
  const pickedT = new Set(geo.tambons);

  const toggleDistrict = (dKey: string, tambonKeys: string[]) => {
    const nextD = new Set(pickedD);
    const nextT = new Set(pickedT);
    if (nextD.has(dKey)) {
      nextD.delete(dKey);
      tambonKeys.forEach(k => nextT.delete(k));
    } else {
      nextD.add(dKey);
      tambonKeys.forEach(k => nextT.add(k));
    }
    onChange({ geo: { ...geo, districts: Array.from(nextD), tambons: Array.from(nextT) } });
  };

  const toggleTambon = (tKey: string, dKey: string, allTambonKeysOfDistrict: string[]) => {
    const nextT = new Set(pickedT);
    const nextD = new Set(pickedD);
    if (nextT.has(tKey)) {
      nextT.delete(tKey);
    } else {
      nextT.add(tKey);
      nextD.add(dKey);
    }
    const stillHas = allTambonKeysOfDistrict.some(k => nextT.has(k));
    if (!stillHas) nextD.delete(dKey);
    onChange({ geo: { ...geo, districts: Array.from(nextD), tambons: Array.from(nextT) } });
  };

  const tickAllInProvince = (prov: string) => {
    const districts = (THAI_GEO as Record<string, DistrictData[]>)[prov] || [];
    const nextD = new Set(pickedD);
    const nextT = new Set(pickedT);
    districts.forEach(d => {
      nextD.add(`${prov}::${d.name}`);
      d.tambons.forEach(t => nextT.add(`${prov}::${d.name}::${t.name}`));
    });
    onChange({ geo: { ...geo, districts: Array.from(nextD), tambons: Array.from(nextT) } });
  };

  const clearProvince = (prov: string) => {
    const nextD = new Set(pickedD);
    const nextT = new Set(pickedT);
    ((THAI_GEO as Record<string, DistrictData[]>)[prov] || []).forEach(d => {
      nextD.delete(`${prov}::${d.name}`);
      d.tambons.forEach(t => nextT.delete(`${prov}::${d.name}::${t.name}`));
    });
    onChange({ geo: { ...geo, districts: Array.from(nextD), tambons: Array.from(nextT) } });
  };

  if (candidateProvinces.length === 0) {
    return (
      <div className="p-card" style={{ padding: 16, borderStyle: 'dashed', textAlign: 'center' }}>
        <div className="p-mono p-fg-dim" style={{ fontSize: 10.5, letterSpacing: '0.08em', marginBottom: 6 }}>อำเภอ / ตำบล</div>
        <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 13.5, lineHeight: 1.5 }}>
          เลือกจังหวัดใน Mode 1 หรือกำหนดรัศมีใน Mode 2 ก่อนนะครับ
          แล้วผมจะดึงอำเภอ/ตำบลในพื้นที่มาให้ท่านปรับเลือก
        </div>
      </div>
    );
  }

  return (
    <div className="p-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--line)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ color: 'var(--accent)' }}><Icons.Pin size={18} /></div>
          <div>
            <div className="p-display" style={{ fontSize: 16 }}>อำเภอ / ตำบล</div>
            <div className="p-fg-dim" style={{ fontSize: 11.5 }}>
              {hasRadius ? 'ติ๊กตามรัศมีให้แล้ว — ปรับเพิ่ม/ออกได้ตามต้องการ' : 'ติ๊กรายอำเภอหรือลงลึกถึงตำบล'}
            </div>
          </div>
        </div>
        <Chip tone="gold" icon={<Icons.Check size={11} />}>{pickedT.size} ตำบล</Chip>
      </div>
      <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {candidateProvinces.map(prov => (
          <ProvinceDistrictGroup
            key={prov}
            province={prov}
            districts={(THAI_GEO as Record<string, DistrictData[]>)[prov] || []}
            pickedD={pickedD}
            pickedT={pickedT}
            inRadiusD={inRadius.districts}
            inRadiusT={inRadius.tambons}
            hasRadius={hasRadius}
            radiusKm={geo.radiusKm}
            gps={geo.gps}
            onToggleDistrict={toggleDistrict}
            onToggleTambon={toggleTambon}
            onTickAll={() => tickAllInProvince(prov)}
            onClearAll={() => clearProvince(prov)}
          />
        ))}
      </div>
    </div>
  );
}

// ── GeoEditor ─────────────────────────────────────────────────────────────────

function SummaryStat({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div style={{ padding: '10px 8px', borderRadius: 8, background: 'var(--surface)', border: '1px solid var(--line)', textAlign: 'center' }}>
      <div style={{ color: 'var(--accent)', display: 'inline-flex', marginBottom: 4 }}>{icon}</div>
      <div className="p-display" style={{ fontSize: 22, lineHeight: 1, color: 'var(--accent)' }}>{value}</div>
      <div className="p-mono p-fg-dim" style={{ fontSize: 9.5, letterSpacing: '0.06em', marginTop: 4, textTransform: 'uppercase' }}>{label}</div>
    </div>
  );
}

function SaveClassSummary({ cls, onSave }: { cls: BusinessClass; onSave: () => void }) {
  const [saved, setSaved] = useState(false);
  const provinces = cls.geo.provinces.length;
  const districts = cls.geo.districts.length;
  const tambons = cls.geo.tambons.length;
  const hasRadius = cls.geo.radiusKm > 0 && cls.geo.gps;

  const handle = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2400);
  };

  if (saved) {
    return (
      <div className="p-gilt" style={{ textAlign: 'center', padding: 24 }}>
        <div style={{ color: 'var(--accent)', marginBottom: 10, display: 'inline-flex' }}><Icons.Check2 size={36} /></div>
        <div className="p-display" style={{ fontSize: 20 }}>บันทึกเสร็จแล้ว</div>
        <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 13, marginTop: 4 }}>
          Sebastian จะใช้พื้นที่นี้คัดกรองงานให้ท่านครับ
        </div>
      </div>
    );
  }

  return (
    <div className="p-gilt">
      <div className="p-mono" style={{ fontSize: 10, letterSpacing: '0.18em', color: 'var(--accent)' }}>สรุปการตั้งค่า</div>
      <div className="p-display" style={{ fontSize: 18, marginTop: 4 }}>{cls.name}</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginTop: 14 }}>
        <SummaryStat label="จังหวัด" value={provinces} icon={<Icons.Map size={13} />} />
        <SummaryStat label="อำเภอ" value={districts} icon={<Icons.Pin size={13} />} />
        <SummaryStat label="ตำบล" value={tambons} icon={<Icons.Check size={13} />} />
      </div>
      {hasRadius && cls.geo.gps && (
        <div style={{ marginTop: 12, padding: '10px 12px', borderRadius: 8, background: 'var(--surface)', border: '1px solid var(--line)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ color: 'var(--accent)' }}><Icons.Compass size={16} /></div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12.5 }}>{cls.geo.gps.label || 'ตำแหน่งโรงงาน'}</div>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.04em' }}>
              รัศมี {cls.geo.radiusKm} กม. · ~{Math.round(Math.PI * cls.geo.radiusKm * cls.geo.radiusKm).toLocaleString()} กม²
            </div>
          </div>
        </div>
      )}
      <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 13, marginTop: 14, lineHeight: 1.5 }}>
        Sebastian จะแจ้งเตือนงานประมูลที่อยู่ในพื้นที่นี้ และตรงกับ keywords ที่ท่านตั้งไว้
      </div>
      <button className="p-btn p-btn-primary" onClick={handle} style={{ width: '100%', marginTop: 14, height: 48, fontSize: 15, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
        <Icons.Check size={16} />บันทึกพื้นที่ครอบคลุม
      </button>
    </div>
  );
}

function GeoEditor({ cls, onChange, onSave }: { cls: BusinessClass; onChange: (patch: Partial<BusinessClass>) => void; onSave: () => void }) {
  const [provinceSearch, setProvinceSearch] = useState('');
  const useProvinces = cls.geo.provinces.length > 0;
  const useRadius = cls.geo.radiusKm > 0 || !!cls.geo.gps;

  const toggleProvince = (p: string) => {
    const list = cls.geo.provinces.includes(p)
      ? cls.geo.provinces.filter(x => x !== p)
      : [...cls.geo.provinces, p];
    onChange({ geo: { ...cls.geo, provinces: list } });
  };

  const filtered = THAI_PROVINCES.filter(p => p.includes(provinceSearch));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <ButlerNote>
        ท่านสามารถเลือกใช้ <span style={{ fontStyle: 'normal', fontFamily: 'var(--font-mono)', fontSize: 12 }}>จังหวัด</span>
        {' '}และ{' '}<span style={{ fontStyle: 'normal', fontFamily: 'var(--font-mono)', fontSize: 12 }}>รัศมีจาก GPS</span>{' '}
        พร้อมกันได้ ระบบจะรวมพื้นที่ทั้งสองให้อัตโนมัติ
      </ButlerNote>

      {/* Mode 1: Provinces */}
      <div className="p-card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--line)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ color: 'var(--accent)' }}><Icons.Map size={18} /></div>
            <div>
              <div className="p-display" style={{ fontSize: 16 }}>Mode 1 · จังหวัด</div>
              <div className="p-fg-dim" style={{ fontSize: 11.5 }}>เลือกพื้นที่แบบรายจังหวัด</div>
            </div>
          </div>
          <Chip tone={useProvinces ? 'gold' : 'outline'}>{cls.geo.provinces.length} จังหวัด</Chip>
        </div>
        <div style={{ padding: 14 }}>
          <input className="p-input" placeholder="ค้นหาจังหวัด..." value={provinceSearch} onChange={e => setProvinceSearch(e.target.value)} style={{ marginBottom: 12 }} />
          {cls.geo.provinces.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 6 }}>เลือกแล้ว</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {cls.geo.provinces.map(p => <Chip key={p} tone="gold" onRemove={() => toggleProvince(p)}>{p}</Chip>)}
              </div>
            </div>
          )}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, maxHeight: 240, overflowY: 'auto', padding: '2px' }}>
            {filtered.map(p => {
              const on = cls.geo.provinces.includes(p);
              return (
                <button key={p} onClick={() => toggleProvince(p)}
                  className={on ? 'p-chip p-chip-gold' : 'p-chip p-chip-outline'}
                  style={{ cursor: 'pointer', border: on ? '1px solid var(--accent-deep)' : '1px solid var(--border)' }}>
                  {on && <Icons.Check size={11} />}
                  {p}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Mode 2: Radius */}
      <div className="p-card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--line)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ color: 'var(--accent)' }}><Icons.Compass size={18} /></div>
            <div>
              <div className="p-display" style={{ fontSize: 16 }}>Mode 2 · รัศมีจากโรงงาน</div>
              <div className="p-fg-dim" style={{ fontSize: 11.5 }}>กำหนดจุด GPS + รัศมี km</div>
            </div>
          </div>
          <Chip tone={useRadius ? 'gold' : 'outline'}>
            {cls.geo.radiusKm > 0 ? `${cls.geo.radiusKm} กม.` : 'ปิด'}
          </Chip>
        </div>
        <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Field label="ชื่อโรงงาน / สถานที่">
            <input className="p-input"
              value={cls.geo.gps?.label || ''}
              onChange={e => onChange({ geo: { ...cls.geo, gps: { ...(cls.geo.gps || { lat: 13.7563, lng: 100.5018 }), label: e.target.value } } })}
              placeholder="เช่น โรงงานบางบอน 4" />
          </Field>
          <GoogleMapsPicker
            current={cls.geo.gps}
            onPick={(lat, lng, label) => onChange({ geo: { ...cls.geo, gps: { lat, lng, label: label || cls.geo.gps?.label || '' } } })}
          />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <Field label="Latitude">
              <input className="p-input" type="number" step="0.0001"
                value={cls.geo.gps?.lat ?? ''}
                onChange={e => onChange({ geo: { ...cls.geo, gps: { ...(cls.geo.gps || { label: '' }), lat: parseFloat(e.target.value) || 0, lng: cls.geo.gps?.lng || 100.5 } } })}
                placeholder="13.7563" />
            </Field>
            <Field label="Longitude">
              <input className="p-input" type="number" step="0.0001"
                value={cls.geo.gps?.lng ?? ''}
                onChange={e => onChange({ geo: { ...cls.geo, gps: { ...(cls.geo.gps || { label: '' }), lng: parseFloat(e.target.value) || 0, lat: cls.geo.gps?.lat || 13.7 } } })}
                placeholder="100.5018" />
            </Field>
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
              <span className="p-label" style={{ margin: 0 }}>รัศมีครอบคลุม</span>
              <span className="p-mono p-fg-accent" style={{ fontSize: 14 }}>{cls.geo.radiusKm} กม.</span>
            </div>
            <input type="range" min="0" max="200" step="5"
              value={cls.geo.radiusKm}
              onChange={e => onChange({ geo: { ...cls.geo, radiusKm: parseInt(e.target.value, 10) } })}
              style={{ width: '100%', accentColor: 'var(--accent)' }} />
            <div className="p-fg-dim p-mono" style={{ fontSize: 10, display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
              <span>0 กม.</span><span>50</span><span>100</span><span>200 กม.</span>
            </div>
          </div>
          {/* Mini map preview — OpenStreetMap via Leaflet */}
          {cls.geo.gps ? (
            <MapPreview lat={cls.geo.gps.lat} lng={cls.geo.gps.lng} radiusKm={cls.geo.radiusKm} />
          ) : (
            <div className="p-mono p-fg-dim" style={{ textAlign: 'center', padding: 20, background: 'var(--surface-2)', borderRadius: 10, fontSize: 11, border: '1px solid var(--line)' }}>
              วาง Google Maps link เพื่อดูแผนที่จริง
            </div>
          )}
          {cls.geo.radiusKm > 0 && (
            <div className="p-mono p-fg-dim" style={{ fontSize: 9.5, letterSpacing: '0.06em', marginTop: 4 }}>
              ~ {Math.round(Math.PI * cls.geo.radiusKm * cls.geo.radiusKm).toLocaleString()} กม²
            </div>
          )}
        </div>
      </div>

      <DistrictTambonPicker cls={cls} onChange={onChange} />
      <SaveClassSummary cls={cls} onSave={onSave} />
    </div>
  );
}

// ── KeywordEditor ─────────────────────────────────────────────────────────────

function KeywordEditor({ cls, onChange, onSave }: { cls: BusinessClass; onChange: (patch: Partial<BusinessClass>) => void; onSave: () => void }) {
  const [input, setInput] = useState('');

  const add = () => {
    const v = input.trim();
    if (!v || cls.keywords.includes(v)) return;
    onChange({ keywords: [...cls.keywords, v] });
    setInput('');
  };

  const remove = (k: string) => onChange({ keywords: cls.keywords.filter(x => x !== k) });

  const custom = cls.keywords.filter(k => !cls.defaultKeywords.includes(k));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <ButlerNote>
        เลือกประเภทธุรกิจที่รับ — Sebastian จะค้นหางานที่มี keywords เหล่านี้ให้อัตโนมัติ
      </ButlerNote>

      {/* ประเภทธุรกิจ checkboxes */}
      <div>
        <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 8 }}>ประเภทธุรกิจที่รับ</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {CLASS_SUGGESTIONS.map(s => {
            const defaultsForType = (DEFAULT_KEYWORDS_BY_CLASS as Record<string, string[]>)[s] || [];
            const isSelected = defaultsForType.length > 0 && defaultsForType.some(k => cls.keywords.includes(k));
            return (
              <button key={s}
                className={isSelected ? 'p-chip p-chip-gold' : 'p-chip p-chip-outline'}
                style={{ cursor: 'pointer', border: isSelected ? '1px solid var(--accent-deep)' : '1px solid var(--border)' }}
                onClick={() => {
                  if (isSelected) {
                    onChange({ keywords: cls.keywords.filter(k => !defaultsForType.includes(k)) });
                  } else {
                    onChange({ keywords: Array.from(new Set([...cls.keywords, ...defaultsForType])) });
                  }
                }}>
                {isSelected && <Icons.Check size={10} />}{s}
              </button>
            );
          })}
        </div>
      </div>

      {/* Custom keywords */}
      <div style={{ display: 'flex', gap: 8 }}>
        <input className="p-input" placeholder="เพิ่ม keyword เพิ่มเติม..." value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && add()} style={{ flex: 1 }} />
        <button className="p-btn p-btn-primary" onClick={add} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Icons.Plus size={14} />เพิ่ม
        </button>
      </div>

      {custom.length > 0 && (
        <div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 8 }}>CUSTOM ที่เพิ่มเอง · {custom.length}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {custom.map(k => <Chip key={k} tone="outline" onRemove={() => remove(k)}>{k}</Chip>)}
          </div>
        </div>
      )}

      {cls.keywords.length > 0 && (
        <div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 8 }}>Keywords ทั้งหมด ({cls.keywords.length})</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {cls.keywords.map(k => <Chip key={k} tone="gold" icon={<Diamond size={5} />} onRemove={() => remove(k)}>{k}</Chip>)}
          </div>
        </div>
      )}

      <button className="p-btn p-btn-primary" onClick={onSave} style={{ width: '100%', marginTop: 4, height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
        <Icons.Check size={16} />บันทึก ({cls.keywords.length} keywords)
      </button>
    </div>
  );
}

// ── FilterEditor ──────────────────────────────────────────────────────────────

function FilterEditor({ cls, onChange, onSave }: { cls: BusinessClass; onChange: (patch: Partial<BusinessClass>) => void; onSave: () => void }) {
  const budgetMin = cls.budgetMinBaht ?? 100000;
  const budgetMax = cls.budgetMaxBaht ?? 50000000;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <ButlerNote>
        Sebastian จะแจ้งเตือนงานที่ตรงกับตัวกรองนี้ — ตั้งค่าแยกกันได้ต่อบริษัท
      </ButlerNote>

      <Field label="งบขั้นต่ำ (บาท)">
        <input className="p-input" type="number" step="100000" min="0"
          value={budgetMin}
          onChange={e => onChange({ budgetMinBaht: parseInt(e.target.value) || 0 })}
          placeholder="100000" />
        <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 4 }}>= {(budgetMin / 1000000).toFixed(2)} ล้านบาท</div>
      </Field>

      <Field label="งบสูงสุด (บาท)">
        <input className="p-input" type="number" step="1000000" min="0"
          value={budgetMax}
          onChange={e => onChange({ budgetMaxBaht: parseInt(e.target.value) || 0 })}
          placeholder="50000000" />
        <div className="p-fg-dim" style={{ fontSize: 11, marginTop: 4 }}>= {(budgetMax / 1000000).toFixed(2)} ล้านบาท</div>
      </Field>

      <div className="p-card" style={{ padding: '0 16px' }}>
        <div style={{ borderBottom: '1px solid var(--line)' }}>
          <Toggle value={cls.isSME ?? false} onChange={v => onChange({ isSME: v })}
            label="บริษัทเป็น SME" hint="แสดงงานที่กำหนด SME ได้" />
        </div>
        <Toggle value={cls.isMIT ?? false} onChange={v => onChange({ isMIT: v })}
          label="สินค้า Made in Thailand" hint="แสดงงานที่กำหนด MIT" />
      </div>

      <Field label="เวลาแจ้งเตือน" hint="Sebastian จะส่ง LINE ตามเวลานี้">
        <input className="p-input" type="time"
          value={cls.notifyTime ?? '06:00'}
          onChange={e => onChange({ notifyTime: e.target.value })} />
      </Field>

      <button className="p-btn p-btn-primary" onClick={onSave}
        style={{ width: '100%', height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
        <Icons.Check size={16} />บันทึกตัวกรอง
      </button>
    </div>
  );
}

// ── DocsEditor ────────────────────────────────────────────────────────────────

function DocsEditor({ cls, onChange }: { cls: BusinessClass; onChange: (patch: Partial<BusinessClass>) => void }) {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const files = cls.files ?? [];

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setUploadError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('companyId', cls.id);
      const res = await fetch('/api/portal/upload', { method: 'POST', body: fd });
      if (!res.ok) { const d = await res.json(); setUploadError(d.error || 'อัปโหลดล้มเหลว'); return; }
      const data = await res.json();
      const newFile: CompanyFile = { name: data.name, url: data.url, uploadedAt: new Date().toISOString(), sizeBytes: data.sizeBytes };
      onChange({ files: [...files, newFile] });
    } catch { setUploadError('เกิดข้อผิดพลาด'); }
    finally { setUploading(false); e.target.value = ''; }
  };

  const removeFile = (url: string) => onChange({ files: files.filter(f => f.url !== url) });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <ButlerNote>
        อัปโหลดเอกสารที่เกี่ยวข้อง — Sebastian จะช่วยอ่านและสรุปข้อมูลสำคัญ
      </ButlerNote>
      <label className="p-btn p-btn-ghost" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, cursor: 'pointer' }}>
        <Icons.Plus size={16} />
        {uploading ? 'กำลังอัปโหลด…' : 'เลือกไฟล์'}
        <input type="file" accept=".pdf,.doc,.docx,.xlsx,.jpg,.png" onChange={handleUpload} style={{ display: 'none' }} disabled={uploading} />
      </label>
      {uploadError && <div style={{ color: 'var(--wine-soft)', fontSize: 13 }}>{uploadError}</div>}
      {files.length === 0 && <div className="p-fg-dim" style={{ fontSize: 13, fontStyle: 'italic', textAlign: 'center' }}>ยังไม่มีเอกสาร</div>}
      {files.map(f => (
        <div key={f.url} className="p-card" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Icons.Doc size={16} style={{ color: 'var(--accent)', flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</div>
            <div className="p-fg-dim" style={{ fontSize: 11 }}>{(f.sizeBytes / 1024).toFixed(0)} KB · {f.uploadedAt.slice(0, 10)}</div>
          </div>
          <a href={f.url} target="_blank" rel="noreferrer" className="p-icon-btn"><Icons.ChevronRight size={14} /></a>
          <button className="p-icon-btn" onClick={() => removeFile(f.url)} style={{ color: 'var(--wine-soft)' }}><Icons.Trash size={14} /></button>
        </div>
      ))}
    </div>
  );
}

// ── NameEditor ────────────────────────────────────────────────────────────────

function NameEditor({ cls, onChange, onSave }: { cls: BusinessClass; onChange: (patch: Partial<BusinessClass>) => void; onSave: () => void }) {
  const [saved, setSaved] = useState(false);
  return (
    <div>
      <Field label="ชื่อ Business Class">
        <input className="p-input" value={cls.name} onChange={e => onChange({ name: e.target.value })} />
      </Field>
      <button className="p-btn p-btn-primary" onClick={() => { setSaved(true); setTimeout(() => setSaved(false), 2200); }} style={{ width: '100%', marginTop: 12, height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
        {saved ? <><Icons.Check2 size={16} />บันทึกเสร็จแล้ว</> : <><Icons.Check size={16} />บันทึกชื่อ Class</>}
      </button>
    </div>
  );
}

// ── EditClassDrawer ───────────────────────────────────────────────────────────

function EditClassDrawer({ cls, onClose, onChange, onDelete }: {
  cls: BusinessClass;
  onClose: () => void;
  onChange: (patch: Partial<BusinessClass>) => void;
  onDelete: () => void;
}) {
  const [tab, setTab] = useState<'geo' | 'keywords' | 'filter' | 'docs' | 'name'>('geo');
  const [confirmDelete, setConfirmDelete] = useState(false);

  const TAB_LABELS = { geo: 'พื้นที่', keywords: 'ประเภท', filter: 'ตัวกรอง', docs: 'เอกสาร', name: 'ชื่อ' };

  return (
    <div className="p-scrim" onClick={onClose} style={{ alignItems: 'stretch', padding: 0 }}>
      <div onClick={e => e.stopPropagation()} style={{
        width: '100%', maxWidth: 480, marginLeft: 'auto',
        background: 'var(--bg)', display: 'flex', flexDirection: 'column',
        minHeight: '100vh', animation: 'p-fade-up 0.22s ease-out both',
      }}>
        {/* Header */}
        <div style={{ position: 'sticky', top: 0, zIndex: 2, padding: '14px 16px', borderBottom: '1px solid var(--line)', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
          <button className="p-icon-btn" onClick={onClose}><Icons.ChevronLeft size={18} /></button>
          <div style={{ flex: 1, textAlign: 'center', minWidth: 0 }}>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.12em' }}>บริษัทของฉัน</div>
            <div className="p-display" style={{ fontSize: 18, marginTop: 2 }}>{cls.name}</div>
          </div>
          <button className="p-icon-btn" onClick={() => setConfirmDelete(true)} style={{ color: 'var(--wine-soft)' }}><Icons.Trash size={16} /></button>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 2, margin: '10px 12px 4px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: 3 }}>
          {(['geo', 'keywords', 'filter', 'docs', 'name'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{ flex: 1, padding: '7px 4px', borderRadius: 7, border: 'none', fontSize: 11, fontWeight: 500, fontFamily: 'var(--font-sans)', cursor: 'pointer', transition: 'background 0.15s, color 0.15s', background: tab === t ? 'var(--accent)' : 'transparent', color: tab === t ? 'var(--ink-deep)' : 'var(--fg-mute)' }}>
              {TAB_LABELS[t]}
            </button>
          ))}
        </div>

        <div style={{ flex: 1, padding: 16, overflowY: 'auto' }}>
          {tab === 'geo' && <GeoEditor cls={cls} onChange={onChange} onSave={onClose} />}
          {tab === 'keywords' && <KeywordEditor cls={cls} onChange={onChange} onSave={onClose} />}
          {tab === 'filter' && <FilterEditor cls={cls} onChange={onChange} onSave={onClose} />}
          {tab === 'docs' && <DocsEditor cls={cls} onChange={onChange} />}
          {tab === 'name' && <NameEditor cls={cls} onChange={onChange} onSave={onClose} />}
        </div>

        <div style={{ padding: 16, borderTop: '1px solid var(--line)', display: 'flex', gap: 10 }}>
          <button className="p-btn p-btn-ghost" onClick={onClose} style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <Icons.ChevronLeft size={16} />กลับหน้าบริษัท
          </button>
        </div>

        <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="ลบบริษัทนี้?">
          <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14, marginBottom: 16 }}>
            ท่านแน่ใจหรือว่าจะลบ <span style={{ color: 'var(--fg)' }}>{cls.name}</span>?
            Sebastian จะไม่แจ้งเตือนงานที่ตรงกับบริษัทนี้อีก
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="p-btn p-btn-ghost" onClick={() => setConfirmDelete(false)} style={{ flex: 1 }}>ยกเลิก</button>
            <button className="p-btn" onClick={onDelete} style={{ flex: 1, background: 'var(--wine)', borderColor: 'var(--wine)', color: 'white' }}>ลบ</button>
          </div>
        </Modal>
      </div>
    </div>
  );
}

// ── AddClassModal ─────────────────────────────────────────────────────────────

function AddClassModal({ open, onClose, onAdd }: { open: boolean; onClose: () => void; onAdd: (name: string, selectedTypes: string[]) => void }) {
  const [name, setName] = useState('');
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  useEffect(() => { if (open) { setName(''); setSelectedTypes([]); } }, [open]);

  const toggleType = (s: string) =>
    setSelectedTypes(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);

  const canAdd = name.trim() || selectedTypes.length > 0;

  return (
    <Modal open={open} onClose={onClose} title="เพิ่มบริษัท">
      <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 14, marginBottom: 14 }}>
        ระบุชื่อบริษัทและประเภทธุรกิจที่รับ — Sebastian จะตั้ง keywords ให้อัตโนมัติ
      </div>
      <Field label="ชื่อบริษัท">
        <input className="p-input" value={name} onChange={e => setName(e.target.value)} placeholder="เช่น BSC ทรัพย์คอนกรีต" autoFocus />
      </Field>
      <div className="p-mono p-fg-dim" style={{ fontSize: 10.5, letterSpacing: '0.08em', marginBottom: 8 }}>ประเภทธุรกิจที่รับ (เลือกได้หลายอย่าง)</div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 18 }}>
        {CLASS_SUGGESTIONS.map(s => (
          <button key={s} onClick={() => toggleType(s)}
            className={selectedTypes.includes(s) ? 'p-chip p-chip-gold' : 'p-chip p-chip-outline'}
            style={{ cursor: 'pointer', border: selectedTypes.includes(s) ? '1px solid var(--accent-deep)' : '1px solid var(--border)' }}>
            {selectedTypes.includes(s) && <Icons.Check size={10} />}{s}
          </button>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 10 }}>
        <button className="p-btn p-btn-ghost" onClick={onClose} style={{ flex: 1 }}>ยกเลิก</button>
        <button className="p-btn p-btn-primary" onClick={() => onAdd(name, selectedTypes)} disabled={!canAdd} style={{ flex: 1 }}>เพิ่มบริษัท</button>
      </div>
    </Modal>
  );
}

// ── ClassCard ─────────────────────────────────────────────────────────────────

function ClassCard({ cls, onEdit, onDelete }: { cls: BusinessClass; onEdit: () => void; onDelete: () => void }) {
  const coverage: string[] = [];
  if (cls.geo.provinces.length) coverage.push(`${cls.geo.provinces.length} จังหวัด`);
  if (cls.geo.radiusKm > 0) coverage.push(`รัศมี ${cls.geo.radiusKm} กม.`);
  if (cls.geo.districts.length) coverage.push(`${cls.geo.districts.length} อำเภอ`);

  return (
    <div className="p-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12, borderLeft: `3px solid ${cls.color}` }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="p-display" style={{ fontSize: 18, lineHeight: 1.2 }}>{cls.name}</div>
          <div className="p-fg-dim" style={{ fontSize: 11.5, marginTop: 3, fontFamily: 'var(--font-mono)', letterSpacing: '0.02em' }}>
            {coverage.length ? coverage.join(' · ') : 'ยังไม่ได้ตั้งพื้นที่'}
          </div>
        </div>
        <button className="p-icon-btn" onClick={onEdit}><Icons.Edit size={16} /></button>
      </div>
      <div style={{ padding: '0 16px 14px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 6 }}>พื้นที่ครอบคลุม</div>
          {cls.geo.provinces.length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
              {cls.geo.provinces.slice(0, 4).map(p => <Chip key={p} tone="outline" icon={<Icons.Pin size={10} />}>{p}</Chip>)}
              {cls.geo.provinces.length > 4 && <Chip tone="outline">+{cls.geo.provinces.length - 4}</Chip>}
            </div>
          )}
          {cls.geo.gps && cls.geo.radiusKm > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 10, background: 'var(--line)' }}>
              <div style={{ color: cls.color }}><Icons.Compass size={16} /></div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 12.5 }}>{cls.geo.gps.label}</div>
                <div className="p-fg-dim p-mono" style={{ fontSize: 10, letterSpacing: '0.04em' }}>
                  {cls.geo.gps.lat.toFixed(4)}°N · {cls.geo.gps.lng.toFixed(4)}°E · รัศมี {cls.geo.radiusKm} กม.
                </div>
              </div>
            </div>
          )}
        </div>
        <div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 6 }}>ประเภทธุรกิจ / Keywords ({cls.keywords.length})</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {cls.keywords.slice(0, 5).map(k => <Chip key={k} tone="gold">{k}</Chip>)}
            {cls.keywords.length > 5 && <Chip tone="outline">+{cls.keywords.length - 5}</Chip>}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── ClassesClient ─────────────────────────────────────────────────────────────

interface Props {
  lineUserId: string;
  initialClasses: BusinessClass[];
}

export function ClassesClient({ lineUserId, initialClasses }: Props) {
  const [classes, setClasses] = useState<BusinessClass[]>(initialClasses);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);

  const editing = classes.find(c => c.id === editingId) ?? null;

  const addClass = (name: string, selectedTypes: string[] = []) => {
    const finalName = name.trim() || (selectedTypes[0] ?? '');
    if (!finalName) return;
    const allDefaults = Array.from(new Set(
      selectedTypes.flatMap(t => (DEFAULT_KEYWORDS_BY_CLASS as Record<string, string[]>)[t] || [])
    ));
    const defaults = allDefaults.length > 0
      ? allDefaults
      : (DEFAULT_KEYWORDS_BY_CLASS as Record<string, string[]>)[finalName] || [];
    const newClass: BusinessClass = {
      id: `c${Date.now()}`,
      name: finalName,
      color: CLASS_COLORS[classes.length % CLASS_COLORS.length],
      geo: { mode: 'province', provinces: [], districts: [], tambons: [], gps: null, radiusKm: 0 },
      keywords: [...defaults],
      defaultKeywords: defaults,
    };
    setClasses(prev => [...prev, newClass]);
    setShowAdd(false);
    setEditingId(newClass.id);
    saveToServer([...classes, newClass]);
  };

  const updateClass = (id: string, patch: Partial<BusinessClass>) => {
    const updated = classes.map(c => c.id === id ? { ...c, ...patch } : c);
    setClasses(updated);
    saveToServer(updated);
  };

  const removeClass = (id: string) => {
    const updated = classes.filter(c => c.id !== id);
    setClasses(updated);
    saveToServer(updated);
  };

  const saveToServer = async (cls: BusinessClass[]) => {
    setSaving(true);
    try {
      await fetch('/api/portal/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ classes: cls }),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-enter">
      <TopBar
        title="บริษัทของฉัน"
        subtitle={`${classes.length} บริษัทที่ลงทะเบียน`}
        right={
          <button className="p-btn p-btn-primary" onClick={() => setShowAdd(true)} style={{ height: 34, padding: '0 14px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Icons.Plus size={14} />เพิ่ม
          </button>
        }
      />

      <div className="p-page p-page-topbar">
        {saving && (
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', textAlign: 'right', marginBottom: 8 }}>กำลังบันทึก...</div>
        )}

        <div className="p-serif p-fg-mute" style={{ fontSize: 14, fontStyle: 'italic', marginBottom: 16, lineHeight: 1.5 }}>
          ลงทะเบียนบริษัทของท่าน — Sebastian จะใช้ข้อมูลนี้คัดกรองงานประมูลให้ตรงเงื่อนไข
        </div>

        {classes.length === 0 && (
          <div className="p-card" style={{ textAlign: 'center', padding: 32 }}>
            <div style={{ color: 'var(--accent)', display: 'inline-flex', marginBottom: 12 }}>
              <Crest size={42} />
            </div>
            <div className="p-display" style={{ fontSize: 18 }}>ยังไม่มีบริษัท</div>
            <div className="p-fg-mute" style={{ fontSize: 13, marginTop: 6, marginBottom: 14 }}>
              เพิ่มบริษัทของท่านเพื่อเริ่มรับการแจ้งเตือนงานประมูล
            </div>
            <button className="p-btn p-btn-primary" onClick={() => setShowAdd(true)} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <Icons.Plus size={14} />เพิ่มบริษัทแรก
            </button>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {classes.map(cls => (
            <ClassCard key={cls.id} cls={cls} onEdit={() => setEditingId(cls.id)} onDelete={() => removeClass(cls.id)} />
          ))}
        </div>
      </div>

      <AddClassModal open={showAdd} onClose={() => setShowAdd(false)} onAdd={addClass} />

      {editing && (
        <EditClassDrawer
          cls={editing}
          onClose={() => setEditingId(null)}
          onChange={patch => updateClass(editing.id, patch)}
          onDelete={() => { removeClass(editing.id); setEditingId(null); }}
        />
      )}
    </div>
  );
}
