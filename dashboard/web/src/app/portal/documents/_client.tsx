'use client';

import { useState, useRef } from 'react';
import { TopBar, Chip, Icons, ButlerNote } from '../_ui';
import type { BusinessClass, DocumentFile } from '@/lib/portal-data';

// ── Constants ─────────────────────────────────────────────────────────────────

const DOC_CATEGORIES = ['TOR', 'BOQ', 'แบบก่อสร้าง', 'ใบเสนอราคา', 'สัญญา', 'Spec', 'อื่นๆ'] as const;
type DocCategory = typeof DOC_CATEGORIES[number];

function inferCategory(name: string): DocCategory {
  const n = name.toLowerCase();
  if (n.includes('tor') || n.includes('ทีโอร์') || n.includes('ขอบเขต')) return 'TOR';
  if (n.includes('boq') || n.includes('ปริมาณ') || n.includes('bill of quantities')) return 'BOQ';
  if (n.includes('แบบ') || n.includes('drawing') || n.includes('plan')) return 'แบบก่อสร้าง';
  if (n.includes('เสนอ') || n.includes('quotation') || n.includes('bid')) return 'ใบเสนอราคา';
  if (n.includes('สัญญา') || n.includes('contract')) return 'สัญญา';
  if (n.includes('spec') || n.includes('รายละเอียด')) return 'Spec';
  return 'อื่นๆ';
}

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── FileRow ───────────────────────────────────────────────────────────────────

function FileRow({ file, onRemove }: { file: DocumentFile; onRemove: () => void }) {
  const categoryColor: Record<DocCategory, string> = {
    'TOR': 'var(--accent)',
    'BOQ': 'var(--emerald)',
    'แบบก่อสร้าง': 'var(--accent)',
    'ใบเสนอราคา': 'var(--wine-soft)',
    'สัญญา': 'var(--accent-deep)',
    'Spec': 'var(--fg-mute)',
    'อื่นๆ': 'var(--border)',
  };

  return (
    <div className="p-card" style={{ padding: '12px 14px', display: 'flex', alignItems: 'flex-start', gap: 10 }}>
      <div style={{ color: 'var(--accent)', flexShrink: 0, marginTop: 2 }}><Icons.FileText size={16} /></div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</div>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, marginTop: 2, letterSpacing: '0.02em' }}>
              {fmtSize(file.sizeBytes)} · {file.uploadedAt.slice(0, 10)}
            </div>
          </div>
          <span style={{
            padding: '2px 8px', borderRadius: 6, fontSize: 10, fontFamily: 'var(--font-mono)',
            background: 'var(--surface-2)', color: categoryColor[file.category as DocCategory] || 'var(--fg-mute)',
            border: '1px solid var(--line)', flexShrink: 0, letterSpacing: '0.04em',
          }}>{file.category}</span>
        </div>
        {file.summary && (
          <div className="p-serif p-fg-mute" style={{ fontSize: 12, fontStyle: 'italic', marginTop: 6, lineHeight: 1.4 }}>
            <span style={{ color: 'var(--accent)', fontStyle: 'normal', fontFamily: 'var(--font-mono)', fontSize: 10 }}>S · </span>
            {file.summary}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
        <a href={file.url} target="_blank" rel="noreferrer" className="p-icon-btn"><Icons.ChevronRight size={14} /></a>
        <button className="p-icon-btn" onClick={onRemove} style={{ color: 'var(--wine-soft)' }}><Icons.Trash size={14} /></button>
      </div>
    </div>
  );
}

// ── UploadZone ────────────────────────────────────────────────────────────────

function UploadZone({ classId, onUploaded }: { classId: string; onUploaded: (file: DocumentFile) => void }) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadFile = async (file: File) => {
    setUploading(true); setError('');
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('companyId', classId);
      const res = await fetch('/api/portal/upload', { method: 'POST', body: fd });
      if (!res.ok) { const d = await res.json(); setError(d.error || 'อัปโหลดล้มเหลว'); return; }
      const data = await res.json();
      const newFile: DocumentFile = {
        id: `doc_${Date.now()}`,
        name: data.name,
        url: data.url,
        uploadedAt: new Date().toISOString(),
        sizeBytes: data.sizeBytes,
        category: inferCategory(data.name),
      };
      onUploaded(newFile);
    } catch { setError('เกิดข้อผิดพลาด กรุณาลองใหม่'); }
    finally { setUploading(false); }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
    e.target.value = '';
  };

  return (
    <div>
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 12, padding: '20px 16px',
          background: dragging ? 'var(--gold-glow)' : 'var(--surface)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
          cursor: 'pointer', transition: 'border-color 0.15s, background 0.15s',
        }}
      >
        <div style={{ color: dragging ? 'var(--accent)' : 'var(--fg-mute)' }}>
          <Icons.Upload size={26} />
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 14, fontWeight: 500 }}>
            {uploading ? 'กำลังอัปโหลด…' : 'ลากไฟล์มาวางที่นี่ หรือกดเพื่อเลือก'}
          </div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10.5, marginTop: 4, letterSpacing: '0.04em' }}>
            PDF, DOC, DOCX, XLSX, JPG, PNG
          </div>
        </div>
      </div>
      <input ref={inputRef} type="file" accept=".pdf,.doc,.docx,.xlsx,.jpg,.png" onChange={handleChange} style={{ display: 'none' }} disabled={uploading} />
      {error && <div style={{ color: 'var(--wine-soft)', fontSize: 13, marginTop: 8 }}>{error}</div>}
    </div>
  );
}

// ── CompanyDocDrawer ──────────────────────────────────────────────────────────

function CompanyDocDrawer({
  cls,
  files,
  onUploaded,
  onRemove,
}: {
  cls: BusinessClass;
  files: DocumentFile[];
  onUploaded: (file: DocumentFile) => void;
  onRemove: (fileId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [filterCat, setFilterCat] = useState<string>('ทั้งหมด');

  const cats = ['ทั้งหมด', ...DOC_CATEGORIES.filter(c => files.some(f => f.category === c))];
  const displayed = filterCat === 'ทั้งหมด' ? files : files.filter(f => f.category === filterCat);

  return (
    <div className="p-card" style={{ padding: 0, overflow: 'hidden' }}>
      <div
        style={{
          padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12,
          borderLeft: `3px solid ${cls.color || 'var(--accent)'}`, cursor: 'pointer',
        }}
        onClick={() => setOpen(v => !v)}
      >
        <div style={{ color: 'var(--accent)', flexShrink: 0 }}><Icons.Folder size={18} /></div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="p-display" style={{ fontSize: 17, lineHeight: 1.2 }}>{cls.companyName || cls.name}</div>
          <div className="p-mono p-fg-dim" style={{ fontSize: 10.5, marginTop: 2, letterSpacing: '0.02em' }}>
            {files.length} ไฟล์
          </div>
        </div>
        <Chip tone={files.length > 0 ? 'gold' : 'outline'} icon={<Icons.Doc size={11} />}>{files.length}</Chip>
        <Icons.ChevronDown
          size={14}
          style={{ transform: open ? 'none' : 'rotate(-90deg)', transition: 'transform 0.15s', color: 'var(--fg-dim)' }}
        />
      </div>

      {open && (
        <div style={{ padding: '0 16px 16px', borderTop: '1px solid var(--line)' }}>
          <div style={{ paddingTop: 14 }}>
            <UploadZone classId={cls.id} onUploaded={onUploaded} />
          </div>

          {files.length > 0 && (
            <>
              {/* Category filter */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 14, marginBottom: 10 }}>
                {cats.map(c => (
                  <button key={c}
                    className={filterCat === c ? 'p-chip p-chip-gold' : 'p-chip p-chip-outline'}
                    style={{ cursor: 'pointer', fontSize: 11, border: filterCat === c ? '1px solid var(--accent-deep)' : '1px solid var(--border)' }}
                    onClick={() => setFilterCat(c)}>
                    {c}
                  </button>
                ))}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {displayed.map(f => (
                  <FileRow key={f.id} file={f} onRemove={() => onRemove(f.id)} />
                ))}
              </div>
            </>
          )}

          {files.length === 0 && (
            <div className="p-serif p-fg-mute" style={{ fontStyle: 'italic', fontSize: 13, textAlign: 'center', padding: '16px 0' }}>
              Sebastian จะช่วยอ่านและสรุปเอกสารที่ท่านอัปโหลดครับ
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── DocumentsClient ───────────────────────────────────────────────────────────

interface Props {
  lineUserId: string;
  classes: BusinessClass[];
  initialDocuments: Record<string, DocumentFile[]>;
}

export function DocumentsClient({ lineUserId: _lineUserId, classes, initialDocuments }: Props) {
  const [documents, setDocuments] = useState<Record<string, DocumentFile[]>>(initialDocuments);
  const [saving, setSaving] = useState(false);

  const saveToServer = async (docs: Record<string, DocumentFile[]>) => {
    setSaving(true);
    try {
      await fetch('/api/portal/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ documents: docs }),
      });
    } finally { setSaving(false); }
  };

  const handleUploaded = (classId: string, file: DocumentFile) => {
    const next = { ...documents, [classId]: [...(documents[classId] ?? []), file] };
    setDocuments(next);
    saveToServer(next);
  };

  const handleRemove = (classId: string, fileId: string) => {
    const next = { ...documents, [classId]: (documents[classId] ?? []).filter(f => f.id !== fileId) };
    setDocuments(next);
    saveToServer(next);
  };

  const totalFiles = Object.values(documents).reduce((a, arr) => a + arr.length, 0);

  return (
    <div className="p-enter">
      <TopBar
        title="เอกสาร"
        subtitle={`Documents · ${totalFiles} ไฟล์`}
      />
      <div className="p-page p-page-topbar">
        <ButlerNote>
          อัปโหลด TOR, BOQ, แบบก่อสร้าง หรือเอกสารประมูลที่เกี่ยวข้อง — Sebastian จะอ่านและสรุปให้ท่านอัตโนมัติ
        </ButlerNote>

        {saving && (
          <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', textAlign: 'right', marginBottom: 8 }}>กำลังบันทึก...</div>
        )}

        {classes.length === 0 && (
          <div className="p-card" style={{ textAlign: 'center', padding: 32 }}>
            <div style={{ color: 'var(--accent)', display: 'inline-flex', marginBottom: 12 }}><Icons.Folder size={36} /></div>
            <div className="p-display" style={{ fontSize: 18 }}>ยังไม่มีบริษัท</div>
            <div className="p-fg-mute" style={{ fontSize: 13, marginTop: 6 }}>
              เพิ่มบริษัทใน &quot;บริษัท&quot; ก่อน แล้วกลับมาอัปโหลดเอกสารครับท่าน
            </div>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {classes.map(cls => (
            <CompanyDocDrawer
              key={cls.id}
              cls={cls}
              files={documents[cls.id] ?? []}
              onUploaded={file => handleUploaded(cls.id, file)}
              onRemove={fileId => handleRemove(cls.id, fileId)}
            />
          ))}
        </div>

        {/* Future feature hint */}
        {totalFiles > 0 && (
          <div style={{ marginTop: 22 }}>
            <div className="p-mono p-fg-dim" style={{ fontSize: 10, letterSpacing: '0.08em', marginBottom: 10 }}>SEBASTIAN ANALYSIS · กำลังพัฒนา</div>
            <div className="p-card" style={{ padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 12, opacity: 0.75 }}>
              <div style={{ color: 'var(--fg-mute)' }}><Icons.Sparkles size={18} /></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 500 }}>สรุป TOR และ BOQ อัตโนมัติ</div>
                <div className="p-fg-dim" style={{ fontSize: 11.5, marginTop: 2, lineHeight: 1.4 }}>Sebastian จะดึงหัวข้อสำคัญ, คุณสมบัติ, และเงื่อนไขพิเศษออกมาให้</div>
              </div>
              <span className="p-chip p-chip-outline" style={{ fontSize: 9.5, flexShrink: 0 }}>เร็วๆ นี้</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
