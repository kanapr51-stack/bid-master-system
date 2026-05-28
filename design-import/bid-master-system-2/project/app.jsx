// app.jsx — main shell, state, routing, navigation

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "dark",
  "typography": "heavy",
  "dashLayout": "grid",
  "nav": "bottom",
  "tierId": "trial"
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  // --- App state ---
  const [loggedIn, setLoggedIn] = useState(false);
  const [page, setPage] = useState("world");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [state, setState] = useState({
    tierId: t.tierId || "trial",
    chatUsed: 8,
    daysLeft: 14,
    expiryLabel: "02 มิ.ย. 2026",
    classes: SEED_CLASSES,
    profile: SEED_PROFILE,
    jobs: SEED_JOBS,
  });

  // Sync tweak → state for tier
  useEffect(() => {
    if (t.tierId !== state.tierId) {
      setState(s => ({ ...s, tierId: t.tierId, chatUsed: t.tierId === "trial" ? 8 : 3 }));
    }
  }, [t.tierId]);

  // Apply theme to body via data-theme
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", t.theme);
    document.documentElement.setAttribute("data-type", t.typography);
  }, [t.theme, t.typography]);

  const nav = (p) => { setPage(p); setDrawerOpen(false); };

  if (!loggedIn) {
    return (
      <div className="app-shell">
        <PageLogin onLogin={() => { setLoggedIn(true); setPage("world"); }} />
        <TweaksUI t={t} setTweak={setTweak} />
      </div>
    );
  }

  return (
    <div className="app-shell">
      {t.nav === "tabs" && <TopTabsNav page={page} nav={nav} />}
      {t.nav === "sidebar" && drawerOpen && (
        <>
          <div className="sidebar-scrim" onClick={() => setDrawerOpen(false)} />
          <Sidebar page={page} nav={nav} state={state} onClose={() => setDrawerOpen(false)} onLogout={() => setLoggedIn(false)} />
        </>
      )}

      <PageContent
        page={page} setPage={setPage}
        state={state} setState={setState}
        layout={t.dashLayout}
        nav={nav}
        navMode={t.nav}
        onMenuToggle={() => setDrawerOpen(d => !d)}
        onLogout={() => { setLoggedIn(false); setPage("world"); }}
      />

      {t.nav === "bottom" && <BottomNav page={page} nav={nav} />}
      <TweaksUI t={t} setTweak={setTweak} />
    </div>
  );
}

function PageContent({ page, setPage, state, setState, layout, nav, navMode, onMenuToggle, onLogout }) {
  // Inject menu button into TopBar for sidebar mode by overriding TopBar usage — simplest: render menu in topbar via portal
  // For brevity, we inject onMenuToggle into pages that show a top bar via a wrapper context. But we don't have context.
  // Simpler: when nav is sidebar, the topbar in each page already shows a default leftIcon (crest). We wrap pages to add a menu button.

  const wrapped = (node) => navMode === "sidebar" ? (
    <div>
      <button className="icon-btn" onClick={onMenuToggle} style={{
        position: "fixed", top: 14, left: 14, zIndex: 50, background: "var(--surface)", border: "1px solid var(--border)",
      }}>
        <Icons.Menu size={18}/>
      </button>
      {node}
    </div>
  ) : node;

  if (page === "world") return wrapped(<PageWorld state={state} nav={nav} layout={layout} />);
  if (page === "classes") return wrapped(<PageClasses state={state} setState={setState} nav={nav} />);
  if (page === "profile") return wrapped(<PageProfile state={state} setState={setState} onLogout={onLogout} />);
  if (page === "packages") return wrapped(<PagePackage state={state} setState={setState} nav={nav} />);
  return null;
}

/* ============ Navigation variants ============ */
const NAV_ITEMS = [
  { id: "world", label: "หน้าหลัก", icon: Icons.Home },
  { id: "classes", label: "Class", icon: Icons.Layers },
  { id: "profile", label: "โปรไฟล์", icon: Icons.User },
  { id: "packages", label: "แพ็กเกจ", icon: Icons.Crown },
];

function BottomNav({ page, nav }) {
  return (
    <div className="bottom-nav">
      {NAV_ITEMS.map(it => {
        const Icon = it.icon;
        const active = page === it.id;
        return (
          <button key={it.id} className={`nav-item ${active ? "active" : ""}`} onClick={() => nav(it.id)}>
            <Icon size={20} sw={active ? 2 : 1.5}/>
            <span>{it.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function TopTabsNav({ page, nav }) {
  return (
    <div style={{
      position: "sticky", top: 0, zIndex: 25,
      background: "var(--bg)",
      borderBottom: "1px solid var(--line)",
      padding: "12px 16px",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
        <div style={{ color: "var(--accent)" }}><Crest size={26}/></div>
        <div className="display" style={{ fontSize: 18 }}>Sebastian</div>
      </div>
      <div style={{ display: "flex", gap: 4, overflowX: "auto", scrollbarWidth: "none" }}>
        {NAV_ITEMS.map(it => {
          const active = page === it.id;
          return (
            <button key={it.id} onClick={() => nav(it.id)} style={{
              padding: "8px 14px",
              borderRadius: 8, border: "1px solid",
              borderColor: active ? "var(--accent-deep)" : "transparent",
              background: active ? "var(--gold-glow)" : "transparent",
              color: active ? "var(--accent)" : "var(--fg-mute)",
              fontSize: 13,
              fontWeight: active ? 600 : 400,
              whiteSpace: "nowrap",
              fontFamily: "var(--font-sans)",
            }}>
              {it.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Sidebar({ page, nav, state, onClose, onLogout }) {
  const tier = TIERS.find(tt => tt.id === state.tierId) || TIERS[0];
  return (
    <div className="sidebar">
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24, padding: "0 6px" }}>
        <div style={{ color: "var(--accent)" }}><Crest size={32}/></div>
        <div style={{ flex: 1 }}>
          <div className="display" style={{ fontSize: 20 }}>Sebastian</div>
          <div className="fg-dim mono" style={{ fontSize: 10, letterSpacing: "0.08em" }}>MASTER SYSTEM</div>
        </div>
        <button className="icon-btn" onClick={onClose}><Icons.X size={16}/></button>
      </div>

      <div className="gilt-frame" style={{ marginBottom: 20, padding: 12 }}>
        <div className="mono" style={{ fontSize: 9.5, letterSpacing: "0.18em", color: "var(--accent)" }}>CURRENT TIER</div>
        <div className="display" style={{ fontSize: 16, marginTop: 2 }}>{tier.name}</div>
        <div className="fg-mute" style={{ fontSize: 11, marginTop: 2 }}>{tier.priceLabel}</div>
      </div>

      {NAV_ITEMS.map(it => {
        const Icon = it.icon;
        return (
          <button key={it.id} className={`sidebar-item ${page === it.id ? "active" : ""}`} onClick={() => nav(it.id)}>
            <Icon size={18}/>
            <span style={{ flex: 1, textAlign: "left" }}>{it.label}</span>
            {page === it.id && <Diamond size={5}/>}
          </button>
        );
      })}

      <div style={{ flex: 1 }} />
      <button className="sidebar-item" onClick={onLogout} style={{ color: "var(--wine-soft)" }}>
        <Icons.LogOut size={18}/>
        <span>ออกจากระบบ</span>
      </button>
    </div>
  );
}

/* ============ Tweaks UI ============ */
function TweaksUI({ t, setTweak }) {
  return (
    <TweaksPanel title="Tweaks · Sebastian">
      <TweakSection label="ธีมสี" />
      <TweakRadio
        label="Theme"
        value={t.theme}
        options={[
          { value: "dark", label: "Ink (Dark)" },
          { value: "light", label: "Manor (Light)" },
          { value: "mixed", label: "Twilight" },
        ]}
        onChange={(v) => setTweak("theme", v)}
      />

      <TweakSection label="ตัวอักษร" />
      <TweakRadio
        label="Typography"
        value={t.typography}
        options={[
          { value: "heavy", label: "Heavy Serif" },
          { value: "modern", label: "Modern Mix" },
        ]}
        onChange={(v) => setTweak("typography", v)}
      />

      <TweakSection label="Dashboard Layout" />
      <TweakRadio
        label="Layout"
        value={t.dashLayout}
        options={[
          { value: "grid", label: "Grid" },
          { value: "list", label: "List" },
          { value: "split", label: "Split" },
        ]}
        onChange={(v) => setTweak("dashLayout", v)}
      />

      <TweakSection label="Navigation" />
      <TweakRadio
        label="Style"
        value={t.nav}
        options={[
          { value: "bottom", label: "Bottom" },
          { value: "tabs", label: "Top Tabs" },
          { value: "sidebar", label: "Sidebar" },
        ]}
        onChange={(v) => setTweak("nav", v)}
      />

      <TweakSection label="Subscription Tier (Demo)" />
      <TweakSelect
        label="Tier"
        value={t.tierId}
        options={TIERS.map(tt => ({ value: tt.id, label: `${tt.name} · ${tt.priceLabel}` }))}
        onChange={(v) => setTweak("tierId", v)}
      />
    </TweaksPanel>
  );
}

// Mount
ReactDOM.createRoot(document.getElementById("root")).render(<App />);
