// page-package.jsx — Package & Upgrade
function PagePackage({ state, setState, nav }) {
  const currentTier = TIERS.find(t => t.id === state.tierId) || TIERS[0];
  const [billing, setBilling] = useState("monthly"); // monthly | annual
  const [selectedId, setSelectedId] = useState(currentTier.id === "trial" ? "standard" : currentTier.id);
  const [step, setStep] = useState("compare"); // compare | confirm | pay | success

  const selected = TIERS.find(t => t.id === selectedId);
  const isCurrent = selected.id === currentTier.id;
  const annualMultiplier = 10; // 2 months free
  const finalPrice = billing === "annual" ? selected.price * annualMultiplier : selected.price;

  return (
    <div className="page-enter">
      <TopBar
        title="แพ็กเกจ"
        subtitle={currentTier.id === "trial" ? `Trial · เหลือ ${state.daysLeft} วัน` : `กำลังใช้ ${currentTier.name}`}
        leftIcon={step !== "compare" ? <Icons.ChevronLeft size={18}/> : null}
        onLeft={() => step !== "compare" && setStep("compare")}
      />

      <div className="page page-with-topbar">
        {step === "compare" && <CompareView
          currentId={currentTier.id}
          selectedId={selectedId}
          onSelect={setSelectedId}
          billing={billing}
          setBilling={setBilling}
          onContinue={() => setStep("confirm")}
        />}
        {step === "confirm" && <ConfirmView
          tier={selected}
          isCurrent={isCurrent}
          billing={billing}
          finalPrice={finalPrice}
          onPay={() => setStep("pay")}
          onBack={() => setStep("compare")}
        />}
        {step === "pay" && <PayView
          tier={selected}
          finalPrice={finalPrice}
          billing={billing}
          onDone={() => {
            setState(s => ({ ...s, tierId: selected.id, chatUsed: 0, daysLeft: 30, expiryLabel: "19 มิ.ย. 2026" }));
            setStep("success");
          }}
        />}
        {step === "success" && <SuccessView
          tier={selected}
          onDone={() => nav("world")}
        />}
      </div>
    </div>
  );
}

/* ============ Compare ============ */
function CompareView({ currentId, selectedId, onSelect, billing, setBilling, onContinue }) {
  return (
    <>
      <div className="serif fg-mute" style={{ fontStyle: "italic", fontSize: 14, marginBottom: 16, lineHeight: 1.5 }}>
        ทุกแพ็กเกจเข้าถึงข้อมูลงานประมูลครบเหมือนกัน — ต่างกันที่จำนวนการคุยกับ Sebastian และความสามารถพิเศษ
      </div>

      {/* Billing toggle */}
      <div className="top-tabs" style={{ margin: "0 0 16px" }}>
        <button className={`top-tab ${billing === "monthly" ? "active" : ""}`} onClick={() => setBilling("monthly")}>
          รายเดือน
        </button>
        <button className={`top-tab ${billing === "annual" ? "active" : ""}`} onClick={() => setBilling("annual")}>
          รายปี · ลด 17%
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {TIERS.map(t => (
          <TierCard
            key={t.id}
            tier={t}
            billing={billing}
            isCurrent={t.id === currentId}
            isSelected={t.id === selectedId}
            onSelect={() => onSelect(t.id)}
          />
        ))}
      </div>

      {/* Sticky CTA */}
      <div style={{
        position: "sticky", bottom: 76,
        marginTop: 18,
        background: "var(--bg)",
        padding: "14px 0",
        borderRadius: 12,
      }}>
        <Btn variant="primary" onClick={onContinue} style={{ width: "100%", height: 52, fontSize: 15.5 }}
          icon={<Icons.Crown size={16}/>}>
          {selectedId === currentId ? "ดูรายละเอียดแพ็กเกจ" : `เปลี่ยนเป็น ${TIERS.find(t => t.id === selectedId)?.name}`}
        </Btn>
      </div>
    </>
  );
}

function TierCard({ tier, billing, isCurrent, isSelected, onSelect }) {
  const monthly = tier.price;
  const annual = monthly * 10;
  const displayPrice = billing === "annual" ? annual : monthly;
  const isFree = monthly === 0;

  return (
    <button onClick={onSelect} className="card" style={{
      textAlign: "left",
      padding: 0,
      cursor: "pointer",
      position: "relative",
      borderColor: isSelected ? "var(--accent)" : "var(--border)",
      borderWidth: isSelected ? 1 : 1,
      boxShadow: isSelected ? "0 0 0 1px var(--accent), 0 0 24px var(--gold-glow)" : "none",
      transition: "all 0.18s",
    }}>
      {tier.popular && (
        <div style={{
          position: "absolute", top: -10, left: 16,
          background: "var(--accent)", color: "var(--ink-deep)",
          padding: "3px 10px", borderRadius: 999,
          fontSize: 10, fontWeight: 700, letterSpacing: "0.1em",
          fontFamily: "var(--font-mono)",
          whiteSpace: "nowrap",
        }}>POPULAR</div>
      )}
      {isCurrent && (
        <div style={{
          position: "absolute", top: -10, right: 16,
          background: "var(--surface)", color: "var(--accent)",
          padding: "3px 10px", borderRadius: 999,
          fontSize: 10, fontWeight: 600, letterSpacing: "0.1em",
          fontFamily: "var(--font-mono)",
          border: "1px solid var(--accent-deep)",
          whiteSpace: "nowrap",
        }}>กำลังใช้</div>
      )}

      <div style={{ padding: 18 }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12, justifyContent: "space-between" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="display" style={{ fontSize: 22, lineHeight: 1.1 }}>{tier.name}</div>
            <div className="fg-mute" style={{ fontSize: 12, marginTop: 2 }}>{tier.nameTh}</div>
          </div>
          <div style={{
            width: 22, height: 22, borderRadius: "50%",
            border: `1.5px solid ${isSelected ? "var(--accent)" : "var(--border)"}`,
            background: isSelected ? "var(--accent)" : "transparent",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "var(--ink-deep)", flexShrink: 0,
            marginTop: isCurrent ? 14 : 0,
          }}>
            {isSelected && <Icons.Check size={13} sw={2.5}/>}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 14 }}>
          {isFree ? (
            <>
              <span className="display fg-accent" style={{ fontSize: 36 }}>ฟรี</span>
              <span className="fg-mute" style={{ fontSize: 13 }}>· 30 วัน</span>
            </>
          ) : (
            <>
              <span className="display fg-accent" style={{ fontSize: 36 }}>
                {displayPrice.toLocaleString()}
              </span>
              <span className="fg-mute" style={{ fontSize: 14 }}>฿ / {billing === "annual" ? "ปี" : "เดือน"}</span>
            </>
          )}
        </div>

        {/* Sebastian Chat callout */}
        <div style={{
          marginTop: 14, padding: "10px 12px",
          background: "var(--gold-glow)", borderRadius: 8,
          border: "1px solid var(--accent-deep)",
          display: "flex", alignItems: "center", gap: 8,
        }}>
          <div style={{ color: "var(--accent)" }}><Icons.Bot size={16}/></div>
          <div>
            <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.06em" }}>SEBASTIAN CHAT</div>
            <div className="serif fg-accent" style={{ fontSize: 14, fontWeight: 500 }}>{tier.chatLabel}</div>
          </div>
        </div>

        {/* Perks */}
        <ul style={{ listStyle: "none", padding: 0, margin: "14px 0 0", display: "flex", flexDirection: "column", gap: 6 }}>
          {tier.perks.map((p, i) => (
            <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 13, lineHeight: 1.4 }}>
              <span style={{ color: "var(--accent)", marginTop: 2, flexShrink: 0 }}>
                <Diamond size={5} color="var(--accent)" />
              </span>
              <span>{p}</span>
            </li>
          ))}
        </ul>

        <div className="serif fg-dim" style={{ fontStyle: "italic", fontSize: 12, marginTop: 14, lineHeight: 1.4 }}>
          {tier.note}
        </div>
      </div>
    </button>
  );
}

/* ============ Confirm ============ */
function ConfirmView({ tier, isCurrent, billing, finalPrice, onPay, onBack }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <ButlerNote tone="gold">
        ขอสรุปแพ็กเกจที่ท่านเลือกครับ — โปรดตรวจสอบรายละเอียดก่อนชำระเงิน
      </ButlerNote>

      <div className="gilt-frame">
        <div className="mono" style={{ fontSize: 10, letterSpacing: "0.18em", color: "var(--accent)" }}>
          ORDER SUMMARY
        </div>
        <div className="display" style={{ fontSize: 26, marginTop: 4 }}>
          Sebastian · {tier.name}
        </div>
        <div className="fg-mute" style={{ fontSize: 13, marginTop: 2 }}>
          {tier.nameTh} · {billing === "annual" ? "ชำระรายปี" : "ชำระรายเดือน"}
        </div>

        <div style={{ borderTop: "1px solid var(--line)", marginTop: 16, paddingTop: 14 }}>
          <Row label="แพ็กเกจ" value={`${tier.name} (${tier.nameTh})`} />
          <Row label="รอบบิล" value={billing === "annual" ? "รายปี · ลด 17%" : "รายเดือน"} />
          <Row label="Sebastian Chat" value={tier.chatLabel} accent />
          <Row label="VAT 7%" value={`${Math.round(finalPrice * 0.07).toLocaleString()} ฿`} />
        </div>

        <div style={{ borderTop: "1px solid var(--line)", marginTop: 14, paddingTop: 14, display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div className="display" style={{ fontSize: 18 }}>ยอดชำระทั้งหมด</div>
          <div className="display fg-accent" style={{ fontSize: 32 }}>
            {Math.round(finalPrice * 1.07).toLocaleString()}<span className="fg-mute" style={{ fontSize: 14, marginLeft: 4 }}>฿</span>
          </div>
        </div>
      </div>

      {/* Payment method */}
      <div className="card">
        <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em", marginBottom: 10 }}>
          วิธีชำระเงิน
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: 12,
          padding: "12px 14px", borderRadius: 10,
          background: "var(--surface-2)",
          border: "1px solid var(--accent-deep)",
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: "linear-gradient(135deg, #3b3a7a, #c93164)",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "white", fontWeight: 700, fontSize: 12, letterSpacing: "0.04em",
            fontFamily: "var(--font-mono)",
          }}>PP</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 500 }}>PromptPay QR</div>
            <div className="fg-dim" style={{ fontSize: 12 }}>สแกนเพื่อชำระทันที</div>
          </div>
          <Icons.Check size={18} style={{ color: "var(--accent)" }}/>
        </div>
      </div>

      <div style={{ display: "flex", gap: 10 }}>
        <Btn variant="ghost" onClick={onBack} style={{ flex: 1 }}>กลับ</Btn>
        <Btn variant="primary" onClick={onPay} style={{ flex: 2 }} icon={<Icons.Coin size={16}/>}>
          ดำเนินการชำระเงิน
        </Btn>
      </div>
    </div>
  );
}

function Row({ label, value, accent }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "6px 0", gap: 12 }}>
      <span className="fg-mute" style={{ fontSize: 13 }}>{label}</span>
      <span style={{ fontSize: 13.5, fontWeight: 500, color: accent ? "var(--accent)" : "inherit", textAlign: "right" }}>{value}</span>
    </div>
  );
}

/* ============ Pay ============ */
function PayView({ tier, finalPrice, billing, onDone }) {
  const [seconds, setSeconds] = useState(300);
  useEffect(() => {
    const t = setInterval(() => setSeconds(s => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, []);
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, alignItems: "center", textAlign: "center" }}>
      <div className="mono" style={{ fontSize: 10, letterSpacing: "0.18em", color: "var(--accent)" }}>
        PROMPTPAY QR
      </div>
      <div className="display" style={{ fontSize: 24 }}>
        สแกนเพื่อชำระ {Math.round(finalPrice * 1.07).toLocaleString()} ฿
      </div>

      <div className="gilt-frame" style={{ background: "var(--surface)" }}>
        <div className="qr-placeholder" />
        <div className="mono" style={{ fontSize: 11, letterSpacing: "0.08em", marginTop: 16, color: "var(--fg-mute)", textAlign: "center" }}>
          QR หมดอายุใน <span style={{ color: "var(--accent)", fontSize: 16, fontWeight: 600 }}>{mm}:{ss}</span>
        </div>
      </div>

      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 8, alignItems: "stretch" }}>
        <div className="card card-tight" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="fg-mute" style={{ fontSize: 12 }}>เลขที่อ้างอิง</span>
          <span className="mono" style={{ fontSize: 12.5, letterSpacing: "0.04em" }}>SB-2026-{Math.floor(Math.random() * 9000 + 1000)}</span>
        </div>
        <div className="card card-tight" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span className="fg-mute" style={{ fontSize: 12 }}>ผู้รับเงิน</span>
          <span style={{ fontSize: 12.5 }}>Manor Master System Co., Ltd.</span>
        </div>
      </div>

      <Btn variant="primary" onClick={onDone} style={{ width: "100%", marginTop: 8 }} icon={<Icons.Check size={16}/>}>
        ยืนยันว่าชำระแล้ว (Demo)
      </Btn>
      <div className="fg-dim" style={{ fontSize: 11.5, fontStyle: "italic" }}>
        ระบบจะตรวจสอบและยืนยันอัตโนมัติภายใน 30 วินาที
      </div>
    </div>
  );
}

/* ============ Success ============ */
function SuccessView({ tier, onDone }) {
  return (
    <div className="page-enter" style={{
      display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center",
      padding: "32px 8px",
    }}>
      <div className="crest-frame" style={{ marginBottom: 18 }}>
        <div style={{
          width: 96, height: 96, borderRadius: 14,
          background: "var(--gold-glow)", border: "1px solid var(--accent)",
          display: "flex", alignItems: "center", justifyContent: "center",
          color: "var(--accent)",
        }}>
          <Icons.Check size={48} sw={1.5}/>
        </div>
      </div>

      <div className="mono" style={{ fontSize: 10, letterSpacing: "0.2em", color: "var(--accent)", marginBottom: 8 }}>
        PAYMENT SUCCESS
      </div>
      <div className="display" style={{ fontSize: 30 }}>ยินดีต้อนรับท่าน</div>
      <div className="serif" style={{ fontSize: 18, marginTop: 6, fontStyle: "italic", color: "var(--fg-mute)" }}>
        สู่ Sebastian · {tier.name}
      </div>

      <div style={{ marginTop: 24, maxWidth: 360 }}>
        <ButlerNote tone="gold">
          ผมพร้อมรับใช้ท่านเต็มที่แล้วครับ — ตั้งแต่บัดนี้เป็นต้นไป
          ท่านสามารถปรึกษาผมใน LINE ได้ {tier.chatLabel}
        </ButlerNote>
      </div>

      <Btn variant="primary" onClick={onDone} style={{ width: "100%", maxWidth: 360, marginTop: 24 }}>
        กลับสู่ Company World
      </Btn>
    </div>
  );
}

window.PagePackage = PagePackage;
