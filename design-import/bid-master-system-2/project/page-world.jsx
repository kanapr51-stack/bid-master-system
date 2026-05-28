// page-world.jsx — Company World (Dashboard)
function PageWorld({ state, nav, layout }) {
  const tier = TIERS.find(t => t.id === state.tierId) || TIERS[0];
  const totalArea = useMemo(() => {
    // crude approximation: per-class union — for demo we just sum unique provinces
    const set = new Set();
    let radiusArea = 0;
    state.classes.forEach(c => {
      c.geo.provinces.forEach(p => set.add(p));
      if (c.geo.radiusKm > 0) radiusArea += Math.PI * c.geo.radiusKm * c.geo.radiusKm;
    });
    return { provinces: set.size, radiusKm2: Math.round(radiusArea) };
  }, [state.classes]);

  const totalKeywords = state.classes.reduce((a, c) => a + c.keywords.length, 0);
  const biddingJobs = state.jobs.filter(j => j.stage === "bidding");
  const pretorJobs = state.jobs.filter(j => j.stage === "pretor");
  const todayMatches = state.jobs.length;
  const isUnlimited = tier.chatQuota === -1;
  const quotaPct = isUnlimited ? 100 : Math.round(((tier.chatQuota - state.chatUsed) / tier.chatQuota) * 100);

  const [feedTab, setFeedTab] = useState("bidding");
  const recentJobs = (feedTab === "bidding" ? biddingJobs : pretorJobs).slice(0, 5);

  return (
    <div className="page-enter">
      <TopBar
        title="Company World"
        subtitle={state.profile.companyName}
        right={
          <div style={{ display: "flex", gap: 6 }}>
            <button className="icon-btn" onClick={() => nav("packages")} title="แพ็กเกจ">
              <Icons.Crown size={18}/>
            </button>
            <button className="icon-btn" title="แจ้งเตือน">
              <Icons.Bell size={18}/>
            </button>
          </div>
        }
      />

      <div className="page page-with-topbar">
        {/* Subscription tier banner */}
        <div className="gilt-frame" style={{ marginBottom: 14 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="mono" style={{ fontSize: 10, letterSpacing: "0.18em", color: "var(--accent)" }}>
                CURRENT TIER · {tier.name.toUpperCase()}
              </div>
              <div className="display" style={{ fontSize: 22, marginTop: 4 }}>
                {tier.id === "trial" ? "ทดลองใช้งาน" : tier.nameTh}
              </div>
              <div className="fg-mute" style={{ fontSize: 12.5, marginTop: 2 }}>
                {tier.id === "trial"
                  ? `เหลือ ${state.daysLeft} วัน · หมดอายุ ${state.expiryLabel}`
                  : `ต่ออายุอัตโนมัติ · ${state.expiryLabel}`}
              </div>
            </div>
            <Btn variant="primary" size="sm" onClick={() => nav("packages")} icon={<Icons.Crown size={14}/>} style={{ whiteSpace: "nowrap" }}>
              {tier.id === "trial" ? "อัปเกรด" : "เปลี่ยน"}
            </Btn>
          </div>

          {tier.id === "trial" && (
            <>
              <div className="deadline-bar" style={{ marginTop: 14 }}>
                <span style={{ width: `${(state.daysLeft / 30) * 100}%` }} />
              </div>
              <div className="mono fg-dim" style={{ fontSize: 10, marginTop: 6, letterSpacing: "0.06em", display: "flex", justifyContent: "space-between" }}>
                <span>0 / 30 วัน</span>
                <span>เหลือ {state.daysLeft}</span>
              </div>
            </>
          )}
        </div>

        {/* Sebastian quota card */}
        <div className="card" style={{ marginBottom: 14, display: "flex", alignItems: "center", gap: 14 }}>
          <QuotaRing pct={quotaPct} unlimited={isUnlimited} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="smallcaps fg-mute">Sebastian Chat</div>
            <div className="display" style={{ fontSize: 22, marginTop: 2 }}>
              {isUnlimited
                ? "ไม่จำกัด"
                : <>เหลือ <span style={{ color: "var(--accent)" }}>{tier.chatQuota - state.chatUsed}</span> / {tier.chatQuota}</>
              }
            </div>
            <div className="fg-dim" style={{ fontSize: 11.5, marginTop: 2 }}>
              {isUnlimited ? "ปรึกษา Sebastian ใน LINE ได้ตลอดเวลา" : `ใช้ไป ${state.chatUsed} ครั้งเดือนนี้`}
            </div>
          </div>
        </div>

        {/* Summary cards */}
        {layout === "split" ? (
          <SummarySplit state={state} nav={nav} totalArea={totalArea} totalKeywords={totalKeywords} todayMatches={todayMatches} />
        ) : layout === "list" ? (
          <SummaryList state={state} nav={nav} totalArea={totalArea} totalKeywords={totalKeywords} todayMatches={todayMatches} />
        ) : (
          <SummaryGrid state={state} nav={nav} totalArea={totalArea} totalKeywords={totalKeywords} todayMatches={todayMatches} />
        )}

        {/* Recent matches */}
        <div style={{ marginTop: 22, marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 10 }}>
            <div>
              <div className="smallcaps fg-mute">งานที่ Sebastian พบล่าสุด</div>
              <div className="display" style={{ fontSize: 20, marginTop: 2 }}>Recent Matches</div>
            </div>
            <Chip tone="gold" icon={<Diamond size={5}/>}>{todayMatches} วันนี้</Chip>
          </div>

          {/* Stage tabs */}
          <div style={{
            display: "flex", gap: 4, padding: 4,
            background: "var(--surface)", border: "1px solid var(--border)",
            borderRadius: 10,
          }}>
            <FeedTab
              active={feedTab === "bidding"}
              onClick={() => setFeedTab("bidding")}
              label="กำลังประมูล"
              sublabel="Bidding"
              count={biddingJobs.length}
              icon={<Icons.Bell size={12}/>}
            />
            <FeedTab
              active={feedTab === "pretor"}
              onClick={() => setFeedTab("pretor")}
              label="Pre-TOR"
              sublabel="ร่าง TOR"
              count={pretorJobs.length}
              icon={<Icons.Doc size={12}/>}
            />
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {recentJobs.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: 28 }}>
              <div className="serif fg-mute" style={{ fontStyle: "italic", fontSize: 14 }}>
                ยังไม่พบงานในประเภทนี้ ผมจะแจ้งให้ทราบทันทีที่พบครับท่าน
              </div>
            </div>
          ) : feedTab === "bidding" ? (
            recentJobs.map(job => <JobCard key={job.id} job={job} cls={state.classes.find(c => c.id === job.matchedClass)} />)
          ) : (
            recentJobs.map(job => <PretorCard key={job.id} job={job} cls={state.classes.find(c => c.id === job.matchedClass)} />)
          )}
        </div>

        {/* Sebastian's note */}
        <div style={{ marginTop: 18 }}>
          <ButlerNote tone="gold">
            {feedTab === "bidding" ? (
              <>ท่านครับ — วันนี้ผมพบงานที่กำลังประมูล <span className="mono" style={{ fontSize: 13 }}>{biddingJobs.length}</span> งาน
              งานที่ปิดเร็วที่สุดเหลือ <span className="mono fg-accent" style={{ fontSize: 13, fontStyle: "normal" }}>{Math.min(...biddingJobs.map(j=>j.daysLeft))} วัน</span> ขอแนะนำให้ดูก่อนนะครับ</>
            ) : (
              <>นอกจากงานประมูลแล้ว ผมยังพบ <span className="mono" style={{ fontStyle: "normal", fontSize: 13 }}>Pre-TOR {pretorJobs.length} ร่าง</span> — ท่านสามารถส่งความเห็นได้ก่อนประกาศจริง เพื่อเตรียมตัวล่วงหน้าครับ</>
            )}
          </ButlerNote>
        </div>

        {/* Upgrade CTA — only if trial */}
        {tier.id === "trial" && (
          <div style={{ marginTop: 18 }}>
            <Btn variant="primary" onClick={() => nav("packages")} icon={<Icons.Crown size={16}/>} style={{ width: "100%" }}>
              อัปเกรดเพื่อใช้งานต่อหลังหมดทดลอง
            </Btn>
          </div>
        )}
      </div>
    </div>
  );
}

/* ============ Quota Ring ============ */
function QuotaRing({ pct, unlimited }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const dash = unlimited ? c : c * (pct / 100);
  return (
    <div style={{ width: 64, height: 64, position: "relative" }}>
      <svg width="64" height="64" viewBox="0 0 64 64" style={{ transform: "rotate(-90deg)" }}>
        <circle cx="32" cy="32" r={r} stroke="var(--border)" strokeWidth="4" fill="none" />
        <circle cx="32" cy="32" r={r} stroke="var(--accent)" strokeWidth="4" fill="none"
          strokeDasharray={`${dash} ${c}`} strokeLinecap="round" />
      </svg>
      <div style={{
        position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
        color: "var(--accent)",
      }}>
        {unlimited
          ? <Icons.Sparkles size={22}/>
          : <span className="display" style={{ fontSize: 16 }}>{pct}%</span>}
      </div>
    </div>
  );
}

/* ============ Summary layouts ============ */
function SummaryGrid({ state, nav, totalArea, totalKeywords, todayMatches }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
      <SumCard
        icon={<Icons.Layers size={16}/>}
        label="Business Class"
        value={state.classes.length}
        unit="ประเภท"
        onClick={() => nav("classes")}
      />
      <SumCard
        icon={<Icons.Map size={16}/>}
        label="พื้นที่ครอบคลุม"
        value={totalArea.provinces}
        unit="จังหวัด"
        sub={totalArea.radiusKm2 ? `+ ${totalArea.radiusKm2.toLocaleString()} กม²` : null}
        onClick={() => nav("classes")}
      />
      <SumCard
        icon={<Icons.Tag size={16}/>}
        label="Keywords"
        value={totalKeywords}
        unit="คำค้น"
        onClick={() => nav("classes")}
      />
      <SumCard
        icon={<Icons.Bell size={16}/>}
        label="งานวันนี้"
        value={todayMatches}
        unit="ที่ตรงเงื่อนไข"
        accent
      />
    </div>
  );
}

function SummaryList({ state, nav, totalArea, totalKeywords, todayMatches }) {
  const items = [
    { icon: <Icons.Layers size={16}/>, label: "Business Class", value: `${state.classes.length} ประเภท`, onClick: () => nav("classes") },
    { icon: <Icons.Map size={16}/>, label: "พื้นที่ครอบคลุม", value: `${totalArea.provinces} จังหวัด${totalArea.radiusKm2 ? ` + ${totalArea.radiusKm2.toLocaleString()} กม²` : ""}`, onClick: () => nav("classes") },
    { icon: <Icons.Tag size={16}/>, label: "Keywords", value: `${totalKeywords} คำค้น`, onClick: () => nav("classes") },
    { icon: <Icons.Bell size={16}/>, label: "งานที่ตรงเงื่อนไขวันนี้", value: `${todayMatches} งาน`, accent: true },
  ];
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      {items.map((it, i) => (
        <button key={i} onClick={it.onClick} style={{
          width: "100%", border: 0, background: "transparent",
          padding: "14px 16px", textAlign: "left",
          display: "flex", alignItems: "center", gap: 12,
          borderTop: i > 0 ? "1px solid var(--line)" : 0,
          color: "var(--fg)",
        }}>
          <div style={{ color: it.accent ? "var(--accent)" : "var(--fg-mute)" }}>{it.icon}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="fg-mute" style={{ fontSize: 12 }}>{it.label}</div>
            <div className="display" style={{ fontSize: 18, marginTop: 2, color: it.accent ? "var(--accent)" : "inherit" }}>{it.value}</div>
          </div>
          {it.onClick && <Icons.ChevronRight size={16} className="fg-dim" />}
        </button>
      ))}
    </div>
  );
}

function SummarySplit({ state, nav, totalArea, totalKeywords, todayMatches }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 10 }}>
      <div className="card" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", background: "var(--gold-glow)", borderColor: "var(--accent-deep)" }}>
        <div className="smallcaps" style={{ color: "var(--accent)" }}>งานวันนี้</div>
        <div>
          <div className="display" style={{ fontSize: 48, color: "var(--accent)", lineHeight: 1 }}>{todayMatches}</div>
          <div className="fg-mute" style={{ fontSize: 12, marginTop: 6 }}>ที่ตรงเงื่อนไขของท่าน</div>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <SumCard small icon={<Icons.Layers size={14}/>} label="Class" value={state.classes.length} unit="ประเภท" onClick={() => nav("classes")} />
        <SumCard small icon={<Icons.Map size={14}/>} label="พื้นที่" value={totalArea.provinces} unit="จังหวัด" onClick={() => nav("classes")} />
        <SumCard small icon={<Icons.Tag size={14}/>} label="Keywords" value={totalKeywords} unit="คำ" onClick={() => nav("classes")} />
      </div>
    </div>
  );
}

function SumCard({ icon, label, value, unit, sub, accent, onClick, small }) {
  return (
    <button onClick={onClick} className="card" style={{
      textAlign: "left", display: "flex", flexDirection: "column", gap: small ? 4 : 8,
      padding: small ? 12 : 16,
      cursor: onClick ? "pointer" : "default",
      borderColor: accent ? "var(--accent-deep)" : "var(--border)",
      background: accent ? "var(--gold-glow)" : "var(--surface)",
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", color: accent ? "var(--accent)" : "var(--fg-mute)" }}>
        {icon}
        {onClick && !small && <Icons.ChevronRight size={14} />}
      </div>
      <div>
        <div className="fg-mute" style={{ fontSize: small ? 10.5 : 11.5, fontFamily: "var(--font-mono)", letterSpacing: "0.04em", textTransform: "uppercase" }}>{label}</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 4 }}>
          <span className="display" style={{ fontSize: small ? 22 : 30, color: accent ? "var(--accent)" : "inherit", lineHeight: 1 }}>{value}</span>
          <span className="fg-dim" style={{ fontSize: small ? 10 : 12 }}>{unit}</span>
        </div>
        {sub && <div className="fg-dim" style={{ fontSize: 11, marginTop: 4 }}>{sub}</div>}
      </div>
    </button>
  );
}

/* ============ Job Card ============ */
function JobCard({ job, cls }) {
  const urgency = job.daysLeft <= 5 ? "wine" : job.daysLeft <= 10 ? "gold" : "outline";
  return (
    <div className="card card-tight surface-card" style={{ padding: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="fg-mute" style={{ fontSize: 11, fontFamily: "var(--font-mono)", letterSpacing: "0.04em", marginBottom: 4 }}>
            {job.agency}
          </div>
          <div className="display" style={{ fontSize: 15.5, lineHeight: 1.3 }}>
            {job.title}
          </div>
        </div>
        <Chip tone={urgency} icon={<Icons.Clock size={11}/>}>
          {job.daysLeft} วัน
        </Chip>
      </div>

      <div style={{ display: "flex", gap: 16, marginTop: 10, alignItems: "center", flexWrap: "wrap" }}>
        <div>
          <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em" }}>งบประมาณ</div>
          <div className="serif" style={{ fontSize: 16, fontWeight: 500 }}>
            <span className="fg-accent">{job.budget.toLocaleString()}</span> <span className="fg-dim" style={{ fontSize: 11 }}>ลบ.</span>
          </div>
        </div>
        {cls && (
          <div style={{ paddingLeft: 16, borderLeft: "1px solid var(--line)" }}>
            <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em" }}>ตรงกับ Class</div>
            <div style={{ fontSize: 13, marginTop: 2, color: cls.color }}>{cls.name}</div>
          </div>
        )}
        {job.distance && (
          <div style={{ paddingLeft: 16, borderLeft: "1px solid var(--line)" }}>
            <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em" }}>ระยะทาง</div>
            <div className="serif" style={{ fontSize: 14 }}>{job.distance} <span className="fg-dim" style={{ fontSize: 11 }}>กม.</span></div>
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 6, marginTop: 12, flexWrap: "wrap" }}>
        {job.matchedKeywords.slice(0, 3).map(k => <Chip key={k} tone="outline">{k}</Chip>)}
        {job.sme && <Chip tone="emerald">SME +7.5%</Chip>}
        {job.mit && <Chip tone="emerald">MIT</Chip>}
      </div>
    </div>
  );
}

/* ============ Feed tab pill ============ */
function FeedTab({ active, onClick, label, sublabel, count, icon }) {
  return (
    <button onClick={onClick} style={{
      flex: 1, padding: "10px 12px",
      borderRadius: 8, border: 0,
      background: active ? "var(--accent)" : "transparent",
      color: active ? "var(--ink-deep)" : "var(--fg-mute)",
      display: "flex", alignItems: "center", gap: 8,
      cursor: "pointer", textAlign: "left",
      transition: "background 0.16s",
      whiteSpace: "nowrap",
      minWidth: 0,
    }}>
      <span style={{ flexShrink: 0 }}>{icon}</span>
      <span style={{
        flex: 1, minWidth: 0,
        fontSize: 13, fontWeight: active ? 700 : 600, letterSpacing: "0.005em",
        overflow: "hidden", textOverflow: "ellipsis",
      }}>{label}</span>
      <span className="mono" style={{
        flexShrink: 0,
        fontSize: 10, letterSpacing: "0.04em",
        padding: "1px 7px", borderRadius: 999,
        background: active ? "rgba(14,13,11,0.20)" : "var(--line)",
        fontWeight: 600,
      }}>{count}</span>
    </button>
  );
}

/* ============ Pre-TOR Card ============ */
function PretorCard({ job, cls }) {
  return (
    <div className="card card-tight surface-card" style={{ padding: 14, position: "relative", overflow: "hidden" }}>
      {/* Stage strip */}
      <div style={{
        position: "absolute", top: 0, left: 0,
        background: "var(--surface-2)",
        borderRight: "1px solid var(--accent-deep)",
        borderBottom: "1px solid var(--accent-deep)",
        borderBottomRightRadius: 8,
        padding: "3px 10px",
        display: "flex", alignItems: "center", gap: 6,
        color: "var(--accent)",
      }}>
        <Icons.Doc size={11}/>
        <span className="mono" style={{ fontSize: 9.5, letterSpacing: "0.12em", fontWeight: 600 }}>
          PRE-TOR
        </span>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start", marginTop: 18 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="fg-mute" style={{ fontSize: 11, fontFamily: "var(--font-mono)", letterSpacing: "0.04em", marginBottom: 4 }}>
            {job.agency}
          </div>
          <div className="display" style={{ fontSize: 15.5, lineHeight: 1.3 }}>
            {job.title}
          </div>
        </div>
      </div>

      {/* Phase indicator (steps) */}
      <div style={{ marginTop: 12 }}>
        <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.06em", marginBottom: 6 }}>
          ขั้นตอน: <span style={{ color: "var(--accent)" }}>{job.pretorPhase}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <PhaseDot label="ร่าง" active />
          <PhaseLine active />
          <PhaseDot label="รับฟัง" active />
          <PhaseLine />
          <PhaseDot label="สรุป" />
          <PhaseLine />
          <PhaseDot label="ประมูล" />
        </div>
      </div>

      {/* Details */}
      <div style={{ display: "flex", gap: 14, marginTop: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div>
          <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em" }}>งบประมาณ</div>
          <div className="serif" style={{ fontSize: 16, fontWeight: 500 }}>
            <span className="fg-accent">{job.budget.toLocaleString()}</span> <span className="fg-dim" style={{ fontSize: 11 }}>ลบ.</span>
          </div>
        </div>
        <div style={{ paddingLeft: 14, borderLeft: "1px solid var(--line)" }}>
          <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em" }}>ปิดรับความเห็น</div>
          <div className="serif" style={{ fontSize: 14 }}>
            <span style={{ color: job.daysToComment <= 7 ? "var(--wine-soft)" : "var(--fg)" }}>
              {job.daysToComment}
            </span> <span className="fg-dim" style={{ fontSize: 11 }}>วัน</span>
          </div>
        </div>
        <div style={{ paddingLeft: 14, borderLeft: "1px solid var(--line)" }}>
          <div className="mono fg-dim" style={{ fontSize: 10, letterSpacing: "0.08em" }}>คาดประมูล</div>
          <div className="serif" style={{ fontSize: 13 }}>{job.expectedBidDate}</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 6, marginTop: 12, flexWrap: "wrap" }}>
        {cls && <Chip tone="outline" icon={<Diamond size={5} color={cls.color}/>}>{cls.name}</Chip>}
        {job.matchedKeywords.slice(0, 2).map(k => <Chip key={k} tone="outline">{k}</Chip>)}
        {job.sme && <Chip tone="emerald">SME</Chip>}
      </div>
    </div>
  );
}

function PhaseDot({ label, active }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <div style={{
        width: 10, height: 10, borderRadius: "50%",
        background: active ? "var(--accent)" : "var(--border)",
        border: active ? "0" : "1px solid var(--line)",
      }} />
      <span className="mono" style={{
        fontSize: 9, letterSpacing: "0.04em",
        color: active ? "var(--accent)" : "var(--fg-dim)",
      }}>{label}</span>
    </div>
  );
}

function PhaseLine({ active }) {
  return (
    <div style={{
      flex: 1, height: 1, marginBottom: 14,
      background: active ? "var(--accent-deep)" : "var(--border)",
    }} />
  );
}

window.PageWorld = PageWorld;
