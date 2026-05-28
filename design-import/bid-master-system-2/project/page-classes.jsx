// page-classes.jsx — Business Class Setup
function PageClasses({ state, setState, nav }) {
  const [editingId, setEditingId] = useState(null);
  const [showAdd, setShowAdd] = useState(false);

  const editing = state.classes.find(c => c.id === editingId);

  const addClass = (name) => {
    if (!name.trim()) return;
    const defaults = DEFAULT_KEYWORDS_BY_CLASS[name.trim()] || [];
    const newClass = {
      id: `c${Date.now()}`,
      name: name.trim(),
      color: ["#C8A86A", "#8B2A36", "#4A7C59", "#5B5448"][state.classes.length % 4],
      geo: { mode: "province", provinces: [], districts: [], tambons: [], gps: null, radiusKm: 0 },
      keywords: [...defaults],
      defaultKeywords: defaults,
    };
    setState(s => ({ ...s, classes: [...s.classes, newClass] }));
    setShowAdd(false);
    setEditingId(newClass.id);
  };

  const updateClass = (id, patch) => {
    setState(s => ({ ...s, classes: s.classes.map(c => c.id === id ? { ...c, ...patch } : c) }));
  };

  const removeClass = (id) => {
    setState(s => ({ ...s, classes: s.classes.filter(c => c.id !== id) }));
  };

  return (
    <div className="page-enter">
      <TopBar
        title="Business Class"
        subtitle={`${state.classes.length} ประเภทธุรกิจ`}
        right={
          <Btn variant="primary" size="sm" icon={<Icons.Plus size={14}/>} onClick={() => setShowAdd(true)}>
            เพิ่ม
          </Btn>
        }
      />

      <div className="page page-with-topbar">
        <div className="serif fg-mute" style={{ fontSize: 14, fontStyle: "italic", marginBottom: 16, lineHeight: 1.5 }}>
          ตั้งค่าประเภทธุรกิจของท่าน — Sebastian จะใช้สิ่งเหล่านี้คัดกรองงานประมูลให้ตรงเงื่อนไข
        </div>

        {state.classes.length === 0 && (
          <div className="card" style={{ textAlign: "center", padding: 32 }}>
            <div style={{ color: "var(--accent)", display: "inline-flex", marginBottom: 12 }}>
              <Crest size={42}/>
            </div>
            <div className="display" style={{ fontSize: 18 }}>ยังไม่มี Business Class</div>
            <div className="fg-mute" style={{ fontSize: 13, marginTop: 6, marginBottom: 14 }}>
              เริ่มต้นโดยเพิ่มประเภทธุรกิจของท่าน
            </div>
            <Btn variant="primary" icon={<Icons.Plus size={14}/>} onClick={() => setShowAdd(true)}>
              เพิ่ม Business Class แรก
            </Btn>
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {state.classes.map(cls => (
            <ClassCard
              key={cls.id}
              cls={cls}
              onEdit={() => setEditingId(cls.id)}
              onDelete={() => removeClass(cls.id)}
            />
          ))}
        </div>
      </div>

      {/* Add modal */}
      <AddClassModal open={showAdd} onClose={() => setShowAdd(false)} onAdd={addClass} />

      {/* Edit drawer */}
      {editing && (
        <EditClassDrawer
          cls={editing}
          onClose={() => setEditingId(null)}
          onChange={(patch) => updateClass(editing.id, patch)}
          onDelete={() => { removeClass(editing.id); setEditingId(null); }}
        />
      )}
    </div>
  );
}

/* ============ Class Card ============ */
function ClassCard({ cls, onEdit, onDelete }) {
  const coverage = [];
  if (cls.geo.provinces.length) coverage.push(`${cls.geo.provinces.length} จังหวัด`);
  if (cls.geo.radiusKm > 0) coverage.push(`รัศมี ${cls.geo.radiusKm} กม.`);
  if (cls.geo.districts.length) coverage.push(`${cls.geo.districts.length} อำเภอ`);

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      {/* Header strip */}
      <div style={{
        padding: "14px 16px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        borderLeft: `3px solid ${cls.color}`,
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="display" style={{ fontSize: 18, lineHeight: 1.2 }}>{cls.name}</div>
          <div className="fg-dim" style={{ fontSize: 11.5, marginTop: 3, fontFamily: "var(--font-mono)", letterSpacing: "0.02em" }}>
            {coverage.length ? coverage.join(" · ") : "ยังไม่ได้ตั้งพื้นที่"}
          </div>
        </div>
        <button className="icon-btn" onClick={onEdit} title="แก้ไข">
          <Icons.Edit size={16}/>
        </button>
      </div>

      {/* Body */}
      <div style={{ padding: "0 16px 14px", display: "flex", flexDirection: "column", gap: 12 }}>
        {/* Coverage row */}
        <div>
          <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em", marginBottom: 6 }}>
            พื้นที่ครอบคลุม
          </div>
          {cls.geo.provinces.length > 0 && (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
              {cls.geo.provinces.slice(0, 4).map(p =>
                <Chip key={p} tone="outline" icon={<Icons.Pin size={10}/>}>{p}</Chip>
              )}
              {cls.geo.provinces.length > 4 && <Chip tone="outline">+{cls.geo.provinces.length - 4}</Chip>}
            </div>
          )}
          {cls.geo.gps && cls.geo.radiusKm > 0 && (
            <div style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "10px 12px", borderRadius: 10,
              background: "var(--line)",
            }}>
              <div style={{ color: cls.color }}>
                <Icons.Compass size={16}/>
              </div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 12.5 }}>{cls.geo.gps.label}</div>
                <div className="fg-dim mono" style={{ fontSize: 10, letterSpacing: "0.04em" }}>
                  {cls.geo.gps.lat.toFixed(4)}°N · {cls.geo.gps.lng.toFixed(4)}°E · รัศมี {cls.geo.radiusKm} กม.
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Keywords */}
        <div>
          <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em", marginBottom: 6 }}>
            Keywords ({cls.keywords.length})
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {cls.keywords.slice(0, 5).map(k =>
              <Chip key={k} tone="gold">{k}</Chip>
            )}
            {cls.keywords.length > 5 && <Chip tone="outline">+{cls.keywords.length - 5}</Chip>}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ============ Add Class Modal ============ */
function AddClassModal({ open, onClose, onAdd }) {
  const [name, setName] = useState("");
  const suggestions = ["คอนกรีตผสมเสร็จ", "ท่ออัดแรง", "รับเหมาก่อสร้าง", "งานโยธา", "งานไฟฟ้า", "งานเหล็ก"];
  useEffect(() => { if (open) setName(""); }, [open]);

  return (
    <Modal open={open} onClose={onClose} title="เพิ่ม Business Class">
      <div className="serif fg-mute" style={{ fontStyle: "italic", fontSize: 14, marginBottom: 14 }}>
        ระบุประเภทธุรกิจที่ท่านรับ — Sebastian จะแนะนำ keywords เริ่มต้นให้
      </div>
      <Field label="ชื่อ Business Class">
        <input className="input" value={name} onChange={e => setName(e.target.value)}
          placeholder="เช่น คอนกรีตผสมเสร็จ" autoFocus />
      </Field>
      <div className="mono fg-dim" style={{ fontSize: 10.5, letterSpacing: "0.08em", marginBottom: 8 }}>
        หรือเลือกจากที่แนะนำ
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 18 }}>
        {suggestions.map(s =>
          <button key={s} onClick={() => setName(s)} className="chip chip-outline"
            style={{ cursor: "pointer", border: "1px solid var(--border)", background: name === s ? "var(--gold-glow)" : "transparent", color: name === s ? "var(--accent)" : "var(--fg-mute)" }}>
            {s}
          </button>
        )}
      </div>
      <div style={{ display: "flex", gap: 10 }}>
        <Btn variant="ghost" onClick={onClose} style={{ flex: 1 }}>ยกเลิก</Btn>
        <Btn variant="primary" onClick={() => onAdd(name)} disabled={!name.trim()} style={{ flex: 1 }}>เพิ่ม Class</Btn>
      </div>
    </Modal>
  );
}

/* ============ Edit Class Drawer ============ */
function EditClassDrawer({ cls, onClose, onChange, onDelete }) {
  const [tab, setTab] = useState("geo"); // geo | keywords
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <div className="modal-scrim" onClick={onClose} style={{ alignItems: "stretch", padding: 0 }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        width: "100%", maxWidth: 480, marginLeft: "auto",
        background: "var(--bg)",
        display: "flex", flexDirection: "column",
        minHeight: "100vh",
        animation: "fadeUp 0.22s ease-out both",
      }}>
        {/* Header */}
        <div style={{
          position: "sticky", top: 0, zIndex: 2,
          padding: "14px 16px", borderBottom: "1px solid var(--line)",
          background: "var(--bg)",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10,
        }}>
          <button className="icon-btn" onClick={onClose}>
            <Icons.ChevronLeft size={18}/>
          </button>
          <div style={{ flex: 1, textAlign: "center", minWidth: 0 }}>
            <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.12em" }}>BUSINESS CLASS</div>
            <div className="display" style={{ fontSize: 18, marginTop: 2 }}>{cls.name}</div>
          </div>
          <button className="icon-btn" onClick={() => setConfirmDelete(true)} style={{ color: "var(--wine-soft)" }}>
            <Icons.Trash size={16}/>
          </button>
        </div>

        {/* Tabs */}
        <div className="top-tabs" style={{ margin: "12px 16px 4px" }}>
          <button className={`top-tab ${tab === "geo" ? "active" : ""}`} onClick={() => setTab("geo")}>
            พื้นที่ครอบคลุม
          </button>
          <button className={`top-tab ${tab === "keywords" ? "active" : ""}`} onClick={() => setTab("keywords")}>
            Keywords
          </button>
          <button className={`top-tab ${tab === "name" ? "active" : ""}`} onClick={() => setTab("name")}>
            ชื่อ Class
          </button>
        </div>

        <div style={{ flex: 1, padding: 16, overflowY: "auto" }}>
          {tab === "geo" && <GeoEditor cls={cls} onChange={onChange} onSave={onClose} />}
          {tab === "keywords" && <KeywordEditor cls={cls} onChange={onChange} onSave={onClose} />}
          {tab === "name" && <NameEditor cls={cls} onChange={onChange} onSave={onClose} />}
        </div>

        {/* Bottom dismiss */}
        <div style={{ padding: 16, borderTop: "1px solid var(--line)", display: "flex", gap: 10 }}>
          <Btn variant="ghost" onClick={onClose} style={{ flex: 1 }} icon={<Icons.ChevronLeft size={16}/>}>
            กลับไปหน้า Class
          </Btn>
        </div>

        {/* Confirm delete */}
        <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="ลบ Business Class?">
          <div className="serif fg-mute" style={{ fontStyle: "italic", fontSize: 14, marginBottom: 16 }}>
            ท่านแน่ใจหรือว่าจะลบ <span style={{ color: "var(--fg)" }}>{cls.name}</span>?
            Sebastian จะไม่แจ้งเตือนงานที่ตรงกับ class นี้อีก
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <Btn variant="ghost" onClick={() => setConfirmDelete(false)} style={{ flex: 1 }}>ยกเลิก</Btn>
            <Btn variant="primary" onClick={onDelete} style={{ flex: 1, background: "var(--wine)", borderColor: "var(--wine)", color: "white" }}>
              ลบ
            </Btn>
          </div>
        </Modal>
      </div>
    </div>
  );
}

function NameEditor({ cls, onChange, onSave }) {
  const [saved, setSaved] = useState(false);
  const handle = () => { setSaved(true); setTimeout(() => setSaved(false), 2200); };
  return (
    <div>
      <Field label="ชื่อ Business Class">
        <input className="input" value={cls.name} onChange={e => onChange({ name: e.target.value })} />
      </Field>
      <Btn variant="primary" onClick={handle} style={{ width: "100%", marginTop: 12 }}
        icon={saved ? <Icons.Check2 size={16}/> : <Icons.Check size={16}/>}>
        {saved ? "บันทึกเสร็จแล้ว" : "บันทึกชื่อ Class"}
      </Btn>
    </div>
  );
}

/* ============ Geo Editor ============ */
function GeoEditor({ cls, onChange, onSave }) {
  const [provinceSearch, setProvinceSearch] = useState("");
  const useProvinces = cls.geo.provinces.length > 0;
  const useRadius = cls.geo.radiusKm > 0 || !!cls.geo.gps;

  const toggleProvince = (p) => {
    const list = cls.geo.provinces.includes(p)
      ? cls.geo.provinces.filter(x => x !== p)
      : [...cls.geo.provinces, p];
    onChange({ geo: { ...cls.geo, provinces: list } });
  };

  const filtered = PROVINCES.filter(p => p.includes(provinceSearch));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <ButlerNote>
        ท่านสามารถเลือกใช้ <span style={{ fontStyle: "normal", fontFamily: "var(--font-mono)", fontSize: 12 }}>จังหวัด</span>
        และ <span style={{ fontStyle: "normal", fontFamily: "var(--font-mono)", fontSize: 12 }}>รัศมีจาก GPS</span> พร้อมกันได้
        ระบบจะรวมพื้นที่ทั้งสองให้อัตโนมัติ
      </ButlerNote>

      {/* Mode 1: Provinces */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{
          padding: "14px 16px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          borderBottom: "1px solid var(--line)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ color: "var(--accent)" }}><Icons.Map size={18}/></div>
            <div>
              <div className="display" style={{ fontSize: 16 }}>Mode 1 · จังหวัด</div>
              <div className="fg-dim" style={{ fontSize: 11.5 }}>เลือกพื้นที่แบบรายจังหวัด</div>
            </div>
          </div>
          <Chip tone={useProvinces ? "gold" : "outline"}>{cls.geo.provinces.length} จังหวัด</Chip>
        </div>

        <div style={{ padding: 14 }}>
          <input className="input" placeholder="ค้นหาจังหวัด..."
            value={provinceSearch} onChange={e => setProvinceSearch(e.target.value)}
            style={{ marginBottom: 12 }} />

          {cls.geo.provinces.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em", marginBottom: 6 }}>เลือกแล้ว</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {cls.geo.provinces.map(p =>
                  <Chip key={p} tone="gold" onRemove={() => toggleProvince(p)}>{p}</Chip>
                )}
              </div>
            </div>
          )}

          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, maxHeight: 240, overflowY: "auto", padding: "2px" }}>
            {filtered.map(p => {
              const on = cls.geo.provinces.includes(p);
              return (
                <button key={p} onClick={() => toggleProvince(p)}
                  className={on ? "chip chip-gold" : "chip chip-outline"}
                  style={{ cursor: "pointer", border: on ? "1px solid var(--accent-deep)" : "1px solid var(--border)" }}>
                  {on && <Icons.Check size={11}/>}
                  {p}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Mode 2: Radius */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{
          padding: "14px 16px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          borderBottom: "1px solid var(--line)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ color: "var(--accent)" }}><Icons.Compass size={18}/></div>
            <div>
              <div className="display" style={{ fontSize: 16 }}>Mode 2 · รัศมีจากโรงงาน</div>
              <div className="fg-dim" style={{ fontSize: 11.5 }}>กำหนดจุด GPS + รัศมี km</div>
            </div>
          </div>
          <Chip tone={useRadius ? "gold" : "outline"}>
            {cls.geo.radiusKm > 0 ? `${cls.geo.radiusKm} กม.` : "ปิด"}
          </Chip>
        </div>

        <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 14 }}>
          <Field label="ชื่อโรงงาน / สถานที่">
            <input className="input"
              value={cls.geo.gps?.label || ""}
              onChange={e => onChange({ geo: { ...cls.geo, gps: { ...(cls.geo.gps || { lat: 13.7563, lng: 100.5018 }), label: e.target.value } } })}
              placeholder="เช่น โรงงานบางบอน 4" />
          </Field>

          <GoogleMapsPicker
            current={cls.geo.gps}
            onPick={(lat, lng, label) => onChange({ geo: { ...cls.geo, gps: { lat, lng, label: label || cls.geo.gps?.label || "" } } })}
          />

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <Field label="Latitude">
              <input className="input" type="number" step="0.0001"
                value={cls.geo.gps?.lat ?? ""}
                onChange={e => onChange({ geo: { ...cls.geo, gps: { ...(cls.geo.gps || { label: "" }), lat: parseFloat(e.target.value) || 0, lng: cls.geo.gps?.lng || 100.5 } } })}
                placeholder="13.7563" />
            </Field>
            <Field label="Longitude">
              <input className="input" type="number" step="0.0001"
                value={cls.geo.gps?.lng ?? ""}
                onChange={e => onChange({ geo: { ...cls.geo, gps: { ...(cls.geo.gps || { label: "" }), lng: parseFloat(e.target.value) || 0, lat: cls.geo.gps?.lat || 13.7 } } })}
                placeholder="100.5018" />
            </Field>
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
              <span className="field-label" style={{ margin: 0 }}>รัศมีครอบคลุม</span>
              <span className="mono fg-accent" style={{ fontSize: 14 }}>{cls.geo.radiusKm} กม.</span>
            </div>
            <input type="range" min="0" max="200" step="5"
              value={cls.geo.radiusKm}
              onChange={e => onChange({ geo: { ...cls.geo, radiusKm: parseInt(e.target.value, 10) } })}
              style={{ width: "100%", accentColor: "var(--accent)" }} />
            <div className="fg-dim mono" style={{ fontSize: 10, display: "flex", justifyContent: "space-between", marginTop: 4 }}>
              <span>0 กม.</span><span>50</span><span>100</span><span>200 กม.</span>
            </div>
          </div>

          {/* Mini map preview */}
          <div style={{
            position: "relative", height: 140, borderRadius: 10,
            background: "var(--surface-2)",
            border: "1px solid var(--line)",
            overflow: "hidden",
            backgroundImage:
              "repeating-linear-gradient(0deg, var(--line) 0 1px, transparent 1px 28px)," +
              "repeating-linear-gradient(90deg, var(--line) 0 1px, transparent 1px 28px)",
          }}>
            {/* Concentric coverage rings */}
            {cls.geo.radiusKm > 0 && (
              <>
                <div style={{
                  position: "absolute", left: "50%", top: "50%",
                  width: Math.min(120, cls.geo.radiusKm * 1.2),
                  height: Math.min(120, cls.geo.radiusKm * 1.2),
                  transform: "translate(-50%, -50%)",
                  borderRadius: "50%",
                  background: "var(--gold-glow)",
                  border: "1px solid var(--accent-deep)",
                }} />
                <div style={{
                  position: "absolute", left: "50%", top: "50%",
                  transform: "translate(-50%, -50%)",
                  width: 12, height: 12, borderRadius: "50%",
                  background: "var(--accent)",
                  boxShadow: "0 0 0 4px var(--bg), 0 0 0 5px var(--accent)",
                }} />
              </>
            )}
            <div className="mono fg-dim" style={{
              position: "absolute", bottom: 8, left: 10,
              fontSize: 9.5, letterSpacing: "0.08em",
            }}>
              MAP PREVIEW
            </div>
            <div className="mono fg-dim" style={{
              position: "absolute", bottom: 8, right: 10,
              fontSize: 9.5, letterSpacing: "0.08em",
            }}>
              ~ {Math.round(Math.PI * cls.geo.radiusKm * cls.geo.radiusKm).toLocaleString()} กม²
            </div>
          </div>
        </div>
      </div>

      {/* District / Tambon picker — combines Mode 1 + Mode 2 selections */}
      <DistrictTambonPicker cls={cls} onChange={onChange} />

      {/* Save summary + action */}
      <SaveClassSummary cls={cls} onSave={onSave} />
    </div>
  );
}
function KeywordEditor({ cls, onChange, onSave }) {
  const [input, setInput] = useState("");
  const [saved, setSaved] = useState(false);
  const handleSave = () => { setSaved(true); setTimeout(() => setSaved(false), 2200); };

  const add = () => {
    const v = input.trim();
    if (!v || cls.keywords.includes(v)) return;
    onChange({ keywords: [...cls.keywords, v] });
    setInput("");
  };

  const remove = (k) => {
    onChange({ keywords: cls.keywords.filter(x => x !== k) });
  };

  const restoreDefaults = () => {
    const merged = Array.from(new Set([...cls.defaultKeywords, ...cls.keywords]));
    onChange({ keywords: merged });
  };

  const custom = cls.keywords.filter(k => !cls.defaultKeywords.includes(k));
  const missingDefaults = cls.defaultKeywords.filter(k => !cls.keywords.includes(k));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <ButlerNote>
        Sebastian จะค้นหางานที่มีคำเหล่านี้ในชื่อหรือรายละเอียด — เพิ่ม keyword ที่เฉพาะเจาะจงเพื่อความแม่นยำมากขึ้นครับท่าน
      </ButlerNote>

      {/* Add row */}
      <div style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          placeholder="พิมพ์ keyword ใหม่..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && add()}
          style={{ flex: 1 }} />
        <Btn variant="primary" onClick={add} icon={<Icons.Plus size={14}/>}>เพิ่ม</Btn>
      </div>

      {/* Default keywords */}
      {cls.defaultKeywords.length > 0 && (
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em" }}>
              KEYWORDS ตั้งต้นสำหรับ {cls.name.toUpperCase()}
            </div>
            {missingDefaults.length > 0 && (
              <button onClick={restoreDefaults} className="mono"
                style={{ background: "transparent", border: 0, color: "var(--accent)", fontSize: 10.5, letterSpacing: "0.04em", textDecoration: "underline", textUnderlineOffset: 3 }}>
                คืนค่าตั้งต้น
              </button>
            )}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {cls.defaultKeywords.map(k => {
              const on = cls.keywords.includes(k);
              return on
                ? <Chip key={k} tone="gold" icon={<Diamond size={5}/>} onRemove={() => remove(k)}>{k}</Chip>
                : <Chip key={k} tone="outline" onRemove={undefined}>
                    <span style={{ opacity: 0.5, textDecoration: "line-through" }}>{k}</span>
                  </Chip>;
            })}
          </div>
        </div>
      )}

      {/* Custom keywords */}
      {custom.length > 0 && (
        <div>
          <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em", marginBottom: 8 }}>
            CUSTOM ที่ท่านเพิ่มเอง · {custom.length}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {custom.map(k =>
              <Chip key={k} tone="outline" onRemove={() => remove(k)}>{k}</Chip>
            )}
          </div>
        </div>
      )}

      <Btn variant="primary" onClick={handleSave} style={{ width: "100%", marginTop: 4 }}
        icon={saved ? <Icons.Check2 size={16}/> : <Icons.Check size={16}/>}>
        {saved ? "บันทึกเสร็จแล้ว" : `บันทึก Keywords (${cls.keywords.length})`}
      </Btn>
    </div>
  );
}

/* ============ Save / Summary card at end of Geo setup ============ */
function SaveClassSummary({ cls, onSave }) {
  const [saved, setSaved] = useState(false);
  const provinces = cls.geo.provinces.length;
  const districts = cls.geo.districts.length;
  const tambons = cls.geo.tambons.length;
  const hasRadius = cls.geo.radiusKm > 0 && cls.geo.gps;

  const handle = () => {
    setSaved(true);
    // Reset back to ready state after a moment so user can re-save subsequent edits
    setTimeout(() => setSaved(false), 2400);
  };

  if (saved) {
    return (
      <div className="gilt-frame" style={{ textAlign: "center", padding: 24 }}>
        <div style={{ color: "var(--accent)", marginBottom: 10, display: "inline-flex" }}>
          <Icons.Check2 size={36}/>
        </div>
        <div className="display" style={{ fontSize: 20 }}>บันทึกเสร็จแล้ว</div>
        <div className="serif fg-mute" style={{ fontStyle: "italic", fontSize: 13, marginTop: 4 }}>
          Sebastian จะใช้พื้นที่นี้คัดกรองงานให้ท่านครับ
        </div>
      </div>
    );
  }

  return (
    <div className="gilt-frame">
      <div className="mono" style={{ fontSize: 10, letterSpacing: "0.18em", color: "var(--accent)" }}>
        สรุปการตั้งค่า
      </div>
      <div className="display" style={{ fontSize: 18, marginTop: 4 }}>
        {cls.name}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginTop: 14 }}>
        <SummaryStat label="จังหวัด" value={provinces} icon={<Icons.Map size={13}/>}/>
        <SummaryStat label="อำเภอ" value={districts} icon={<Icons.Pin size={13}/>}/>
        <SummaryStat label="ตำบล" value={tambons} icon={<Icons.Check size={13}/>}/>
      </div>

      {hasRadius && (
        <div style={{
          marginTop: 12, padding: "10px 12px", borderRadius: 8,
          background: "var(--surface)", border: "1px solid var(--line)",
          display: "flex", alignItems: "center", gap: 10,
        }}>
          <div style={{ color: "var(--accent)" }}><Icons.Compass size={16}/></div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12.5 }}>{cls.geo.gps.label || "ตำแหน่งโรงงาน"}</div>
            <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.04em" }}>
              รัศมี {cls.geo.radiusKm} กม. · ~{Math.round(Math.PI * cls.geo.radiusKm * cls.geo.radiusKm).toLocaleString()} กม²
            </div>
          </div>
        </div>
      )}

      <div className="serif fg-mute" style={{ fontStyle: "italic", fontSize: 13, marginTop: 14, lineHeight: 1.5 }}>
        Sebastian จะแจ้งเตือนงานประมูลที่อยู่ในพื้นที่นี้ และตรงกับ keywords ที่ท่านตั้งไว้
      </div>

      <Btn variant="primary" onClick={handle}
        style={{ width: "100%", marginTop: 14, height: 48, fontSize: 15 }}
        icon={<Icons.Check size={16}/>}>
        บันทึกพื้นที่ครอบคลุม
      </Btn>
    </div>
  );
}

function SummaryStat({ label, value, icon }) {
  return (
    <div style={{
      padding: "10px 8px", borderRadius: 8,
      background: "var(--surface)",
      border: "1px solid var(--line)",
      textAlign: "center",
    }}>
      <div style={{ color: "var(--accent)", display: "inline-flex", marginBottom: 4 }}>{icon}</div>
      <div className="display" style={{ fontSize: 22, lineHeight: 1, color: "var(--accent)" }}>{value}</div>
      <div className="mono fg-dim" style={{ fontSize: 9.5, letterSpacing: "0.06em", marginTop: 4, textTransform: "uppercase" }}>{label}</div>
    </div>
  );
}

window.PageClasses = PageClasses;

/* ============ District / Tambon Picker ============ */
function DistrictTambonPicker({ cls, onChange }) {
  // Compose the candidate districts from:
  //  (a) all provinces in cls.geo.provinces (Mode 1)
  //  (b) any province whose districts contain at least one district within radius (Mode 2)
  const { geo } = cls;
  const hasRadius = geo.gps && geo.radiusKm > 0;

  // For mode 2: which districts/tambons are within radius?
  const inRadius = useMemo(() => {
    if (!hasRadius) return { districts: new Set(), tambons: new Set() };
    const dSet = new Set();
    const tSet = new Set();
    for (const [prov, districts] of Object.entries(THAI_GEO)) {
      for (const d of districts) {
        const dKey = `${prov}::${d.name}`;
        const dDist = distanceKm(geo.gps.lat, geo.gps.lng, d.lat, d.lng);
        if (dDist <= geo.radiusKm) dSet.add(dKey);
        for (const t of d.tambons) {
          const tKey = `${dKey}::${t.name}`;
          const tDist = distanceKm(geo.gps.lat, geo.gps.lng, t.lat, t.lng);
          if (tDist <= geo.radiusKm) tSet.add(tKey);
        }
      }
    }
    return { districts: dSet, tambons: tSet };
  }, [hasRadius, geo.gps?.lat, geo.gps?.lng, geo.radiusKm]);

  // Provinces to show in the picker: union of selected provinces + provinces touched by radius
  const candidateProvinces = useMemo(() => {
    const s = new Set(geo.provinces);
    inRadius.tambons.forEach(key => s.add(key.split("::")[0]));
    inRadius.districts.forEach(key => s.add(key.split("::")[0]));
    return Array.from(s).filter(p => THAI_GEO[p]);
  }, [geo.provinces, inRadius]);

  // Auto-tick by radius once when the radius/GPS changes:
  // merge radius-derived selections into existing picks (non-destructive).
  const radiusSignature = `${geo.gps?.lat || 0}|${geo.gps?.lng || 0}|${geo.radiusKm || 0}`;
  const lastSig = useRef("");
  useEffect(() => {
    if (!hasRadius) return;
    if (lastSig.current === radiusSignature) return;
    lastSig.current = radiusSignature;
    const newDistricts = new Set([...geo.districts, ...inRadius.districts]);
    const newTambons = new Set([...geo.tambons, ...inRadius.tambons]);
    onChange({ geo: {
      ...geo,
      districts: Array.from(newDistricts),
      tambons: Array.from(newTambons),
    }});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [radiusSignature]);

  const pickedD = new Set(geo.districts);
  const pickedT = new Set(geo.tambons);

  const toggleDistrict = (dKey, tambonKeys) => {
    const nextD = new Set(pickedD);
    const nextT = new Set(pickedT);
    if (nextD.has(dKey)) {
      // Untick district → also untick its tambons
      nextD.delete(dKey);
      tambonKeys.forEach(k => nextT.delete(k));
    } else {
      // Tick district → also tick all its tambons
      nextD.add(dKey);
      tambonKeys.forEach(k => nextT.add(k));
    }
    onChange({ geo: { ...geo, districts: Array.from(nextD), tambons: Array.from(nextT) } });
  };

  const toggleTambon = (tKey, dKey, allTambonKeysOfDistrict) => {
    const nextT = new Set(pickedT);
    const nextD = new Set(pickedD);
    if (nextT.has(tKey)) {
      nextT.delete(tKey);
    } else {
      nextT.add(tKey);
      nextD.add(dKey); // ticking any tambon implies district is in-scope
    }
    // If no tambons under district are ticked, untick district too
    const stillHas = allTambonKeysOfDistrict.some(k => nextT.has(k));
    if (!stillHas) nextD.delete(dKey);
    onChange({ geo: { ...geo, districts: Array.from(nextD), tambons: Array.from(nextT) } });
  };

  const tickAllInProvince = (prov) => {
    const districts = THAI_GEO[prov] || [];
    const nextD = new Set(pickedD);
    const nextT = new Set(pickedT);
    districts.forEach(d => {
      nextD.add(`${prov}::${d.name}`);
      d.tambons.forEach(t => nextT.add(`${prov}::${d.name}::${t.name}`));
    });
    onChange({ geo: { ...geo, districts: Array.from(nextD), tambons: Array.from(nextT) } });
  };

  const clearProvince = (prov) => {
    const nextD = new Set(pickedD);
    const nextT = new Set(pickedT);
    (THAI_GEO[prov] || []).forEach(d => {
      nextD.delete(`${prov}::${d.name}`);
      d.tambons.forEach(t => nextT.delete(`${prov}::${d.name}::${t.name}`));
    });
    onChange({ geo: { ...geo, districts: Array.from(nextD), tambons: Array.from(nextT) } });
  };

  if (candidateProvinces.length === 0) {
    return (
      <div className="card" style={{ padding: 16, borderStyle: "dashed", textAlign: "center" }}>
        <div className="mono fg-dim" style={{ fontSize: 10.5, letterSpacing: "0.08em", marginBottom: 6 }}>
          อำเภอ / ตำบล
        </div>
        <div className="serif fg-mute" style={{ fontStyle: "italic", fontSize: 13.5, lineHeight: 1.5 }}>
          เลือกจังหวัดใน Mode 1 หรือกำหนดรัศมีใน Mode 2 ก่อนนะครับ
          แล้วผมจะดึงอำเภอ/ตำบลในพื้นที่มาให้ท่านปรับเลือก
        </div>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <div style={{
        padding: "14px 16px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        borderBottom: "1px solid var(--line)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ color: "var(--accent)" }}><Icons.Pin size={18}/></div>
          <div>
            <div className="display" style={{ fontSize: 16 }}>อำเภอ / ตำบล</div>
            <div className="fg-dim" style={{ fontSize: 11.5 }}>
              {hasRadius ? "ติ๊กตามรัศมีให้แล้ว — ปรับเพิ่ม/ออกได้ตามต้องการ" : "ติ๊กรายอำเภอหรือลงลึกถึงตำบล"}
            </div>
          </div>
        </div>
        <Chip tone="gold" icon={<Icons.Check size={11}/>}>
          {pickedT.size} ตำบล
        </Chip>
      </div>

      <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 16 }}>
        {candidateProvinces.map(prov => (
          <ProvinceDistrictGroup
            key={prov}
            province={prov}
            districts={THAI_GEO[prov] || []}
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

function ProvinceDistrictGroup({
  province, districts, pickedD, pickedT, inRadiusD, inRadiusT,
  hasRadius, radiusKm, gps,
  onToggleDistrict, onToggleTambon, onTickAll, onClearAll,
}) {
  const [expanded, setExpanded] = useState(true);
  const provincePickedTambons = districts.reduce((acc, d) =>
    acc + d.tambons.filter(t => pickedT.has(`${province}::${d.name}::${t.name}`)).length, 0);
  const provinceTotalTambons = districts.reduce((acc, d) => acc + d.tambons.length, 0);

  return (
    <div style={{ borderRadius: 10, border: "1px solid var(--line)", overflow: "hidden" }}>
      <div style={{
        padding: "10px 12px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "var(--surface-2)",
        cursor: "pointer",
      }} onClick={() => setExpanded(!expanded)}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icons.ChevronDown size={14} style={{ transform: expanded ? "none" : "rotate(-90deg)", transition: "transform 0.15s", color: "var(--fg-mute)" }}/>
          <span style={{ fontSize: 14, fontWeight: 500 }}>{province}</span>
          <span className="mono fg-dim" style={{ fontSize: 10.5, letterSpacing: "0.04em" }}>
            {provincePickedTambons}/{provinceTotalTambons} ตำบล
          </span>
        </div>
        <div style={{ display: "flex", gap: 6 }} onClick={(e) => e.stopPropagation()}>
          <button onClick={onTickAll} className="mono" style={{
            background: "transparent", border: "1px solid var(--border)",
            color: "var(--fg-mute)", padding: "2px 8px", borderRadius: 6,
            fontSize: 10, cursor: "pointer", letterSpacing: "0.04em",
          }}>ทั้งหมด</button>
          <button onClick={onClearAll} className="mono" style={{
            background: "transparent", border: "1px solid var(--border)",
            color: "var(--fg-mute)", padding: "2px 8px", borderRadius: 6,
            fontSize: 10, cursor: "pointer", letterSpacing: "0.04em",
          }}>ล้าง</button>
        </div>
      </div>

      {expanded && (
        <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 4 }}>
          {districts.map(d => {
            const dKey = `${province}::${d.name}`;
            const dTambonKeys = d.tambons.map(t => `${dKey}::${t.name}`);
            const dPicked = pickedD.has(dKey);
            const tickedTambons = dTambonKeys.filter(k => pickedT.has(k)).length;
            const partial = tickedTambons > 0 && tickedTambons < d.tambons.length;
            const inRadius = inRadiusD.has(dKey);
            const dist = hasRadius && gps ? distanceKm(gps.lat, gps.lng, d.lat, d.lng) : null;

            return (
              <DistrictRow
                key={dKey}
                district={d}
                dKey={dKey}
                picked={dPicked}
                partial={partial}
                tickedTambons={tickedTambons}
                inRadius={inRadius}
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

function DistrictRow({ district, dKey, picked, partial, tickedTambons, inRadius, distance, pickedT, inRadiusT, hasRadius, gps, onToggleDistrict, onToggleTambon }) {
  const [openTambons, setOpenTambons] = useState(false);

  return (
    <div style={{ borderRadius: 8 }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "8px 10px",
        background: picked ? "var(--gold-glow)" : "transparent",
        borderRadius: 8,
      }}>
        <button onClick={onToggleDistrict} aria-pressed={picked} style={{
          width: 18, height: 18, padding: 0, borderRadius: 4,
          border: `1.5px solid ${picked ? "var(--accent)" : "var(--border)"}`,
          background: picked ? "var(--accent)" : "transparent",
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, cursor: "pointer",
        }}>
          {picked && !partial && <Icons.Check size={11} sw={3} style={{ color: "var(--ink-deep)" }}/>}
          {partial && <div style={{ width: 8, height: 2, background: "var(--ink-deep)" }}/>}
        </button>

        <button onClick={() => setOpenTambons(!openTambons)} style={{
          flex: 1, minWidth: 0,
          border: 0, background: "transparent",
          textAlign: "left", color: "inherit",
          display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
        }}>
          <span style={{ fontSize: 13.5, fontWeight: picked ? 500 : 400 }}>
            อ. {district.name}
          </span>
          {inRadius && hasRadius && (
            <Chip tone="emerald" icon={<Icons.Compass size={10}/>}>
              ในรัศมี{distance ? ` ${Math.round(distance)} กม.` : ""}
            </Chip>
          )}
          <span className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.04em", marginLeft: "auto" }}>
            {tickedTambons}/{district.tambons.length}
          </span>
          <Icons.ChevronDown size={12} style={{ transform: openTambons ? "none" : "rotate(-90deg)", transition: "transform 0.15s", color: "var(--fg-dim)" }}/>
        </button>
      </div>

      {openTambons && (
        <div style={{ padding: "6px 8px 8px 38px", display: "flex", flexWrap: "wrap", gap: 6 }}>
          {district.tambons.map(t => {
            const tKey = `${dKey}::${t.name}`;
            const tPicked = pickedT.has(tKey);
            const tInRadius = inRadiusT.has(tKey);
            const tDist = hasRadius && gps ? distanceKm(gps.lat, gps.lng, t.lat, t.lng) : null;
            return (
              <button key={tKey} onClick={() => onToggleTambon(tKey)}
                className={tPicked ? "chip chip-gold" : "chip chip-outline"}
                style={{
                  cursor: "pointer",
                  border: tPicked ? "1px solid var(--accent-deep)" : "1px solid var(--border)",
                  position: "relative",
                }}>
                {tPicked && <Icons.Check size={10}/>}
                <span>ต. {t.name}</span>
                {tInRadius && hasRadius && !tPicked && (
                  <span title="ในรัศมี" style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--emerald)", marginLeft: 2 }}/>
                )}
                {tDist != null && tPicked && (
                  <span className="mono" style={{ fontSize: 9, opacity: 0.7, marginLeft: 2 }}>
                    {Math.round(tDist)} กม.
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ============ Google Maps link picker ============ */
function parseGoogleMapsUrl(url) {
  if (!url || typeof url !== "string") return null;
  const u = url.trim();

  // Plain "lat, lng" or "lat,lng"
  const plain = u.match(/^(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)$/);
  if (plain) return { lat: parseFloat(plain[1]), lng: parseFloat(plain[2]) };

  // @lat,lng,zoom pattern (the most common URL format)
  const atMatch = u.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/);
  if (atMatch) return { lat: parseFloat(atMatch[1]), lng: parseFloat(atMatch[2]) };

  // ?q=lat,lng or ?ll=lat,lng or &query=lat,lng
  const qMatch = u.match(/[?&](?:q|ll|query|destination)=(-?\d+\.\d+),(-?\d+\.\d+)/);
  if (qMatch) return { lat: parseFloat(qMatch[1]), lng: parseFloat(qMatch[2]) };

  // !3dLAT!4dLNG (place URL embedded coords)
  const placeMatch = u.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
  if (placeMatch) return { lat: parseFloat(placeMatch[1]), lng: parseFloat(placeMatch[2]) };

  return null;
}

function isShortGoogleMapsUrl(url) {
  if (!url) return false;
  return /(?:goo\.gl\/maps|maps\.app\.goo\.gl|g\.co\/kgs)/i.test(url);
}

function extractPlaceName(url) {
  // Try to pull the place name from /place/<name>/
  const m = String(url || "").match(/\/place\/([^/@]+)/);
  if (!m) return "";
  try {
    return decodeURIComponent(m[1].replace(/\+/g, " "));
  } catch {
    return "";
  }
}

function GoogleMapsPicker({ current, onPick }) {
  const [link, setLink] = useState("");
  const [status, setStatus] = useState(null); // null | 'ok' | 'short' | 'invalid'

  const tryParse = (raw) => {
    setLink(raw);
    if (!raw.trim()) { setStatus(null); return; }
    const coords = parseGoogleMapsUrl(raw);
    if (coords) {
      const placeName = extractPlaceName(raw);
      onPick(coords.lat, coords.lng, placeName);
      setStatus("ok");
      return;
    }
    if (isShortGoogleMapsUrl(raw)) { setStatus("short"); return; }
    setStatus("invalid");
  };

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) tryParse(text);
    } catch (e) {
      // fall back to manual entry
    }
  };

  return (
    <div style={{
      padding: 12, borderRadius: 10,
      background: "var(--gold-glow)",
      border: "1px solid var(--accent-deep)",
      marginBottom: 4,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <div style={{ color: "var(--accent)" }}><Icons.Map size={14}/></div>
        <div className="mono" style={{ fontSize: 10.5, letterSpacing: "0.08em", color: "var(--accent)", fontWeight: 600 }}>
          วาง Google Maps Link
        </div>
        <div style={{ flex: 1 }} />
        <button onClick={handlePaste}
          className="mono" style={{
            background: "transparent", border: "1px solid var(--accent-deep)",
            color: "var(--accent)", padding: "3px 9px", borderRadius: 6,
            fontSize: 10.5, letterSpacing: "0.04em", cursor: "pointer",
          }}>
          วางจาก clipboard
        </button>
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          value={link}
          onChange={e => tryParse(e.target.value)}
          placeholder="https://maps.google.com/... หรือ 13.7563, 100.5018"
          style={{ flex: 1, fontSize: 13 }}
        />
      </div>

      {status === "ok" && (
        <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 6, color: "var(--emerald)" }}>
          <Icons.Check size={12} sw={2.5}/>
          <span className="mono" style={{ fontSize: 11, letterSpacing: "0.04em", color: "#88B89B" }}>
            ดึงพิกัดได้แล้ว: {current?.lat?.toFixed(4)}°N · {current?.lng?.toFixed(4)}°E
          </span>
        </div>
      )}
      {status === "short" && (
        <div style={{ marginTop: 8, display: "flex", alignItems: "flex-start", gap: 6, color: "var(--wine-soft)" }}>
          <Icons.Info size={12}/>
          <span className="serif" style={{ fontSize: 12, fontStyle: "italic", lineHeight: 1.4 }}>
            ลิงก์แบบสั้น (goo.gl) ไม่มีพิกัดในตัว กรุณาเปิดลิงก์ใน Google Maps แล้วคัดลอกลิงก์เต็ม (URL bar) หรือพิกัด lat, lng โดยตรง
          </span>
        </div>
      )}
      {status === "invalid" && (
        <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 6, color: "var(--fg-dim)" }}>
          <Icons.Info size={12}/>
          <span className="mono" style={{ fontSize: 10.5, letterSpacing: "0.04em" }}>
            ไม่พบพิกัดในลิงก์นี้
          </span>
        </div>
      )}
      {status === null && (
        <div className="fg-dim" style={{ fontSize: 11, marginTop: 6, fontStyle: "italic", fontFamily: "var(--font-serif)", lineHeight: 1.4 }}>
          วิธีหา: เปิด Google Maps → ค้นหาโรงงาน → คัดลอก URL จาก address bar
        </div>
      )}
    </div>
  );
}
