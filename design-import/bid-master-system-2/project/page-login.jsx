// page-login.jsx
function PageLogin({ onLogin }) {
  const [showTiers, setShowTiers] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleLine = () => {
    setLoading(true);
    setTimeout(() => { setLoading(false); onLogin(); }, 950);
  };

  return (
    <div className="page-enter" style={{
      minHeight: "100vh",
      display: "flex", flexDirection: "column",
      padding: "32px 22px 28px",
      position: "relative",
    }}>
      {/* Decorative top ornament */}
      <div style={{ display: "flex", justifyContent: "center", marginTop: 8 }}>
        <DividerOrnate />
      </div>

      {/* Hero */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", textAlign: "center", padding: "32px 0" }}>
        <div style={{ color: "var(--accent)", display: "flex", justifyContent: "center", marginBottom: 18 }}>
          <Crest size={76} />
        </div>
        <div className="mono" style={{ fontSize: 10.5, letterSpacing: "0.32em", color: "var(--fg-mute)", marginBottom: 10 }}>
          MANOR MASTER SYSTEM
        </div>
        <h1 className="display" style={{ fontSize: 44, margin: "0 0 10px", letterSpacing: "0.005em" }}>
          Sebastian
        </h1>
        <div className="serif" style={{ fontSize: 16, fontStyle: "italic", color: "var(--fg-mute)", lineHeight: 1.5, maxWidth: 320, margin: "0 auto" }}>
          พ่อบ้านส่วนตัวสำหรับผู้รับเหมา —<br/>
          เฝ้าระวังงานประมูลใหม่ วิเคราะห์คู่แข่ง<br/>จัดเอกสารแทนท่าน
        </div>

        <div style={{ marginTop: 28, display: "flex", justifyContent: "center", gap: 8, flexWrap: "wrap" }}>
          <Chip tone="gold" icon={<Icons.Bell size={11}/>}>แจ้งเตือนงาน 06:00 ทุกวัน</Chip>
          <Chip tone="outline" icon={<Icons.Doc size={11}/>}>สรุปเอกสาร</Chip>
          <Chip tone="outline" icon={<Icons.TrendUp size={11}/>}>วิเคราะห์คู่แข่ง</Chip>
        </div>
      </div>

      {/* Login button */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Btn
          variant="line"
          onClick={handleLine}
          disabled={loading}
          icon={
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
              <path d="M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm-2.6 11.4c-.55.62-3.55 4-3.95 4.36-.4.36-.65.21-.65-.2 0-.41.04-1.32.04-1.32-2.7-.35-4.84-2.31-4.84-4.69 0-2.62 2.6-4.75 5.8-4.75s5.8 2.13 5.8 4.75c0 1.07-.43 2.05-1.2 2.85z" />
            </svg>
          }
          style={{ width: "100%", height: 52, fontSize: 15.5 }}>
          {loading ? "กำลังเชื่อมต่อกับ LINE…" : "เข้าสู่ระบบด้วย LINE"}
        </Btn>

        <button
          onClick={() => setShowTiers(true)}
          className="btn-ghost"
          style={{
            background: "transparent", border: 0, color: "var(--fg-mute)",
            padding: "8px", fontSize: 13, textAlign: "center",
            textDecoration: "underline", textUnderlineOffset: 4, textDecorationColor: "var(--accent-deep)",
          }}>
          ดูแพ็กเกจราคา ก่อนเข้าสู่ระบบ
        </button>

        <div className="fg-dim" style={{ fontSize: 11, textAlign: "center", fontFamily: "var(--font-mono)", letterSpacing: "0.04em", marginTop: 4 }}>
          ทดลองใช้ฟรี 30 วัน · ไม่ต้องผูกบัตร
        </div>
      </div>

      {/* Tier preview modal */}
      <Modal open={showTiers} onClose={() => setShowTiers(false)} title="แพ็กเกจของเรา">
        <div className="fg-mute serif" style={{ fontStyle: "italic", marginBottom: 16, fontSize: 14 }}>
          ทุกแพ็กเกจเข้าถึงข้อมูลงานประมูลครบเหมือนกัน ต่างกันที่จำนวนการคุยกับ Sebastian และความสามารถพิเศษ
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {TIERS.map(t => (
            <div key={t.id} className="card" style={{
              padding: 14,
              borderColor: t.popular ? "var(--accent)" : "var(--border)",
              position: "relative",
            }}>
              {t.popular && (
                <div style={{
                  position: "absolute", top: -8, right: 12,
                  background: "var(--accent)", color: "var(--ink-deep)",
                  padding: "2px 10px", borderRadius: 999,
                  fontSize: 10, fontWeight: 700, letterSpacing: "0.08em",
                  fontFamily: "var(--font-mono)",
                }}>POPULAR</div>
              )}
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                <div className="display" style={{ fontSize: 18 }}>{t.name}</div>
                <div className="mono fg-accent" style={{ fontSize: 13 }}>{t.priceLabel}</div>
              </div>
              <div className="fg-mute" style={{ fontSize: 12, marginTop: 2 }}>{t.nameTh}</div>
              <div className="fg-dim" style={{ fontSize: 11.5, marginTop: 8 }}>
                Sebastian Chat: <span style={{ color: "var(--accent)" }}>{t.chatLabel}</span>
              </div>
            </div>
          ))}
        </div>
        <Btn variant="primary" onClick={() => setShowTiers(false)} style={{ width: "100%", marginTop: 16 }}>
          เริ่มต้นใช้งานฟรี 30 วัน
        </Btn>
      </Modal>

      {/* Bottom ornament */}
      <div style={{ display: "flex", justifyContent: "center", marginTop: 28 }}>
        <DividerOrnate />
      </div>
      <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.18em", textAlign: "center", marginTop: 12 }}>
        EST. ANNO MMXXVI · BANGKOK
      </div>
    </div>
  );
}

window.PageLogin = PageLogin;
