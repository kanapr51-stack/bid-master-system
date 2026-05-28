// page-profile.jsx — Company Profile & Settings
function PageProfile({ state, setState, onLogout }) {
  const p = state.profile;
  const update = (patch) => setState(s => ({ ...s, profile: { ...s.profile, ...patch } }));
  const [showLogout, setShowLogout] = useState(false);

  return (
    <div className="page-enter">
      <TopBar
        title="โปรไฟล์บริษัท"
        subtitle="Company Profile"
      />

      <div className="page page-with-topbar">
        {/* Company crest header */}
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          padding: "16px 0 24px", textAlign: "center",
        }}>
          <div className="crest-frame" style={{ marginBottom: 18 }}>
            <div style={{
              width: 84, height: 84, borderRadius: 12,
              background: "var(--surface)", border: "1px solid var(--accent-deep)",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "var(--accent)",
            }}>
              <Crest size={56}/>
            </div>
          </div>
          <div className="display" style={{ fontSize: 22, lineHeight: 1.25, padding: "0 24px", textWrap: "balance" }}>
            {p.companyName}
          </div>
          <div className="mono fg-dim" style={{ fontSize: 11, letterSpacing: "0.08em", marginTop: 8 }}>
            MEMBER · MMXXVI
          </div>

          <div style={{ display: "flex", gap: 6, marginTop: 14, flexWrap: "wrap", justifyContent: "center" }}>
            {p.isSME && <Chip tone="emerald" icon={<Icons.Shield size={11}/>}>SME · แต้มต่อ 7.5%</Chip>}
            {p.isMIT && <Chip tone="emerald" icon={<Icons.Flag size={11}/>}>Made in Thailand</Chip>}
          </div>
        </div>

        <DividerOrnate label="ข้อมูลบริษัท" />

        <Section title="">
          <Field label="ชื่อบริษัท">
            <input className="input" value={p.companyName} onChange={e => update({ companyName: e.target.value })} />
          </Field>
          <Field label="เบอร์โทรศัพท์">
            <input className="input" value={p.phone} onChange={e => update({ phone: e.target.value })}
              placeholder="02-xxx-xxxx" inputMode="tel" />
          </Field>
          <Field label="อีเมล">
            <input className="input" value={p.email} onChange={e => update({ email: e.target.value })}
              placeholder="info@company.co.th" inputMode="email" />
          </Field>
        </Section>

        <DividerOrnate label="ขอบเขตงาน" />

        <Section title="">
          <div style={{ marginBottom: 14 }}>
            <div className="field-label">ช่วงมูลค่างานที่รับ</div>
            <BudgetRange
              min={p.budgetMin} max={p.budgetMax}
              onChange={(min, max) => update({ budgetMin: min, budgetMax: max })}
            />
            <div className="serif" style={{ fontSize: 14, marginTop: 10, fontStyle: "italic", color: "var(--fg-mute)" }}>
              Sebastian จะแจ้งเตือนเฉพาะงานที่อยู่ในช่วง{" "}
              <span className="fg-accent" style={{ fontStyle: "normal" }}>
                {p.budgetMin.toLocaleString()} – {p.budgetMax.toLocaleString()} ล้านบาท
              </span>
            </div>
          </div>
        </Section>

        <DividerOrnate label="คุณสมบัติพิเศษ" />

        <Section title="">
          <div className="card" style={{ padding: "0 16px" }}>
            <div style={{ padding: "4px 0", borderBottom: "1px solid var(--line)" }}>
              <Toggle
                value={p.isSME}
                onChange={(v) => update({ isSME: v })}
                label="บริษัทเป็น SME"
                hint="ได้แต้มต่อ 7.5% ในการประมูลงานภาครัฐ"
              />
            </div>
            <div style={{ padding: "4px 0" }}>
              <Toggle
                value={p.isMIT}
                onChange={(v) => update({ isMIT: v })}
                label="สินค้า Made in Thailand"
                hint="ได้สิทธิ์พิเศษในงานประมูลที่กำหนด MIT"
              />
            </div>
          </div>
        </Section>

        <DividerOrnate label="การแจ้งเตือน" />

        <Section title="">
          <Field label="เวลาแจ้งเตือนงานประจำวัน"
            hint="Sebastian จะส่งสรุปงานใหม่ใน LINE ทุกวันตามเวลานี้">
            <TimePicker value={p.notifyTime} onChange={(v) => update({ notifyTime: v })} />
          </Field>
        </Section>

        {/* Quick stats */}
        <div className="card" style={{ marginTop: 8, marginBottom: 16, padding: 14 }}>
          <div className="smallcaps fg-mute">บัญชีของท่าน</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 10 }}>
            <Stat label="ผู้ใช้ตั้งแต่" value="01.04.2026" />
            <Stat label="เชื่อม LINE" value="✓" valueColor="var(--emerald)" />
            <Stat label="Business Class" value={state.classes.length} />
            <Stat label="งานที่เคยพบ" value="248" />
          </div>
        </div>

        <Btn variant="ghost" onClick={() => setShowLogout(true)}
          icon={<Icons.LogOut size={16}/>}
          style={{ width: "100%", color: "var(--wine-soft)" }}>
          ออกจากระบบ
        </Btn>

        <Modal open={showLogout} onClose={() => setShowLogout(false)} title="ออกจากระบบ?">
          <div className="serif fg-mute" style={{ fontStyle: "italic", fontSize: 14, marginBottom: 16 }}>
            ขอบพระคุณที่ใช้บริการครับท่าน Sebastian จะรอรับใช้ท่านเสมอ
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <Btn variant="ghost" onClick={() => setShowLogout(false)} style={{ flex: 1 }}>ยกเลิก</Btn>
            <Btn variant="primary" onClick={onLogout} style={{ flex: 1, background: "var(--wine)", borderColor: "var(--wine)", color: "white" }}>
              ออกจากระบบ
            </Btn>
          </div>
        </Modal>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ margin: "12px 0 18px" }}>
      {title && <div className="display" style={{ fontSize: 18, marginBottom: 12 }}>{title}</div>}
      {children}
    </div>
  );
}

function Stat({ label, value, valueColor }) {
  return (
    <div>
      <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase" }}>{label}</div>
      <div className="display" style={{ fontSize: 18, marginTop: 2, color: valueColor || "inherit" }}>{value}</div>
    </div>
  );
}

/* ============ Budget range slider (dual handle approximation) ============ */
function BudgetRange({ min, max, onChange }) {
  const MIN = 0.1, MAX = 100;
  const pctMin = ((Math.min(min, MAX) - MIN) / (MAX - MIN)) * 100;
  const pctMax = ((Math.min(max, MAX) - MIN) / (MAX - MIN)) * 100;

  return (
    <div>
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "baseline",
        marginBottom: 12, gap: 8,
      }}>
        <div>
          <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.06em" }}>MIN</div>
          <div className="display fg-accent" style={{ fontSize: 22 }}>{min.toLocaleString()} ลบ.</div>
        </div>
        <div className="fg-dim" style={{ fontSize: 12 }}>—</div>
        <div style={{ textAlign: "right" }}>
          <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.06em" }}>MAX</div>
          <div className="display fg-accent" style={{ fontSize: 22 }}>{max.toLocaleString()} ลบ.</div>
        </div>
      </div>

      {/* Visual track */}
      <div style={{
        position: "relative", height: 6, background: "var(--border)",
        borderRadius: 3, marginBottom: 18,
      }}>
        <div style={{
          position: "absolute", height: "100%",
          left: `${pctMin}%`, right: `${100 - pctMax}%`,
          background: "var(--accent)", borderRadius: 3,
        }} />
        <div style={{
          position: "absolute", top: "50%", transform: "translate(-50%, -50%)",
          left: `${pctMin}%`,
          width: 14, height: 14, background: "var(--accent)", borderRadius: "50%",
          border: "2px solid var(--bg)",
        }} />
        <div style={{
          position: "absolute", top: "50%", transform: "translate(-50%, -50%)",
          left: `${pctMax}%`,
          width: 14, height: 14, background: "var(--accent)", borderRadius: "50%",
          border: "2px solid var(--bg)",
        }} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        <div>
          <div className="mono fg-dim" style={{ fontSize: 10, marginBottom: 4, letterSpacing: "0.06em" }}>MIN (ล้านบาท)</div>
          <input className="input" type="number" step="0.5" min="0.1" max={max - 0.1}
            value={min} onChange={e => onChange(Math.max(0.1, parseFloat(e.target.value) || 0), max)} />
        </div>
        <div>
          <div className="mono fg-dim" style={{ fontSize: 10, marginBottom: 4, letterSpacing: "0.06em" }}>MAX (ล้านบาท)</div>
          <input className="input" type="number" step="0.5" min={min + 0.1} max="500"
            value={max} onChange={e => onChange(min, Math.max(min + 0.1, parseFloat(e.target.value) || 0))} />
        </div>
      </div>
    </div>
  );
}

/* ============ Time Picker ============ */
function TimePicker({ value, onChange }) {
  const hours = ["05:00", "06:00", "07:00", "08:00", "09:00", "12:00", "18:00"];
  return (
    <div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
        {hours.map(h => (
          <button key={h} onClick={() => onChange(h)}
            className={value === h ? "chip chip-gold" : "chip chip-outline"}
            style={{ cursor: "pointer", padding: "8px 14px", fontSize: 13, fontFamily: "var(--font-mono)" }}>
            {h}
          </button>
        ))}
      </div>
      <input className="input" type="time" value={value} onChange={e => onChange(e.target.value)} />
    </div>
  );
}

window.PageProfile = PageProfile;
