// components.jsx — shared UI primitives for Sebastian
const { useState, useEffect, useRef, useMemo, createContext, useContext } = React;

/* ============ ICONS (custom heraldic SVG) ============ */
function Crest({ size = 48, color }) {
  const c = color || "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden>
      <path d="M24 3 L40 9 V22 C40 32 33 40 24 45 C15 40 8 32 8 22 V9 L24 3 Z"
        stroke={c} strokeWidth="1" fill="none" />
      <path d="M24 7 L36 12 V22 C36 30 30 36 24 40 C18 36 12 30 12 22 V12 L24 7 Z"
        stroke={c} strokeWidth="0.5" fill="none" opacity="0.5" />
      <text x="24" y="29" fontFamily="Cormorant Garamond, serif" fontSize="18"
        fontStyle="italic" fontWeight="500" fill={c} textAnchor="middle">S</text>
    </svg>
  );
}

function Fleur({ size = 16, color }) {
  const c = color || "currentColor";
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill={c} aria-hidden>
      <path d="M8 1 L9 6 L14 8 L9 10 L8 15 L7 10 L2 8 L7 6 Z" />
    </svg>
  );
}

function Diamond({ size = 8, color }) {
  return <span style={{
    display: "inline-block",
    width: size, height: size,
    background: color || "var(--accent)",
    transform: "rotate(45deg)",
  }} />;
}

function DividerOrnate({ label }) {
  return (
    <div className="divider-ornate">
      <Diamond size={5} />
      {label && <span className="smallcaps" style={{ color: "var(--fg-mute)" }}>{label}</span>}
      <Diamond size={5} />
    </div>
  );
}

/* ============ Lucide-style line icons ============ */
const Icon = ({ d, size = 18, sw = 1.5 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    {typeof d === "string" ? <path d={d} /> : d}
  </svg>
);

const Icons = {
  Home: (p) => <Icon {...p} d={<><path d="M3 11 12 3l9 8"/><path d="M5 10v10h14V10"/></>}/>,
  Layers: (p) => <Icon {...p} d={<><path d="M12 3 2 8l10 5 10-5-10-5z"/><path d="M2 13l10 5 10-5"/><path d="M2 18l10 5 10-5"/></>}/>,
  User: (p) => <Icon {...p} d={<><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-7 8-7s8 3 8 7"/></>}/>,
  Crown: (p) => <Icon {...p} d="M3 18h18M3 8l5 5 4-7 4 7 5-5v10H3z"/>,
  Bell: (p) => <Icon {...p} d={<><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10 21a2 2 0 0 0 4 0"/></>}/>,
  ChevronRight: (p) => <Icon {...p} d="M9 6l6 6-6 6"/>,
  ChevronDown: (p) => <Icon {...p} d="M6 9l6 6 6-6"/>,
  ChevronLeft: (p) => <Icon {...p} d="M15 6l-6 6 6 6"/>,
  Plus: (p) => <Icon {...p} d="M12 5v14M5 12h14"/>,
  Minus: (p) => <Icon {...p} d="M5 12h14"/>,
  Check: (p) => <Icon {...p} d="M4 12l5 5L20 6"/>,
  X: (p) => <Icon {...p} d="M6 6l12 12M6 18 18 6"/>,
  Search: (p) => <Icon {...p} d={<><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>}/>,
  Map: (p) => <Icon {...p} d={<><path d="M9 3 3 6v15l6-3 6 3 6-3V3l-6 3-6-3z"/><path d="M9 3v15M15 6v15"/></>}/>,
  Pin: (p) => <Icon {...p} d={<><path d="M12 2a7 7 0 0 1 7 7c0 5-7 13-7 13S5 14 5 9a7 7 0 0 1 7-7z"/><circle cx="12" cy="9" r="2.5"/></>}/>,
  Compass: (p) => <Icon {...p} d={<><circle cx="12" cy="12" r="9"/><path d="m16 8-2.5 5.5L8 16l2.5-5.5z"/></>}/>,
  Tag: (p) => <Icon {...p} d={<><path d="M3 12V4h8l10 10-8 8L3 12z"/><circle cx="7.5" cy="7.5" r="1"/></>}/>,
  Clock: (p) => <Icon {...p} d={<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>}/>,
  Phone: (p) => <Icon {...p} d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A15 15 0 0 1 3 6a2 2 0 0 1 2-2z"/>,
  Mail: (p) => <Icon {...p} d={<><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></>}/>,
  Building: (p) => <Icon {...p} d={<><rect x="5" y="3" width="14" height="18"/><path d="M9 7h1M14 7h1M9 11h1M14 11h1M9 15h1M14 15h1M10 21v-4h4v4"/></>}/>,
  Coin: (p) => <Icon {...p} d={<><ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6"/><path d="M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6"/></>}/>,
  Sparkles: (p) => <Icon {...p} d={<><path d="M12 3v5M12 16v5M3 12h5M16 12h5M5 5l3 3M16 16l3 3M19 5l-3 3M8 16l-3 3"/></>}/>,
  Settings: (p) => <Icon {...p} d={<><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>}/>,
  LogOut: (p) => <Icon {...p} d={<><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/></>}/>,
  Trash: (p) => <Icon {...p} d={<><path d="M4 7h16M9 7V4h6v3M6 7v13a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7"/><path d="M10 11v6M14 11v6"/></>}/>,
  Edit: (p) => <Icon {...p} d="M14 4l6 6-12 12H2v-6L14 4z"/>,
  Filter: (p) => <Icon {...p} d="M3 5h18l-7 8v7l-4-2v-5L3 5z"/>,
  Menu: (p) => <Icon {...p} d="M3 6h18M3 12h18M3 18h18"/>,
  Calendar: (p) => <Icon {...p} d={<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/></>}/>,
  Bot: (p) => <Icon {...p} d={<><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M12 8V4M9 4h6"/><circle cx="9" cy="14" r="1"/><circle cx="15" cy="14" r="1"/></>}/>,
  Shield: (p) => <Icon {...p} d="M12 2 4 6v6c0 5 4 9 8 10 4-1 8-5 8-10V6l-8-4z"/>,
  Flag: (p) => <Icon {...p} d={<><path d="M4 21V4"/><path d="M4 4h13l-2 5 2 5H4"/></>}/>,
  TrendUp: (p) => <Icon {...p} d="M3 17l6-6 4 4 8-9M14 6h7v7"/>,
  Doc: (p) => <Icon {...p} d={<><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/><path d="M8 13h8M8 17h6"/></>}/>,
  Info: (p) => <Icon {...p} d={<><circle cx="12" cy="12" r="9"/><path d="M12 8v.5M11 12h1v5h1"/></>}/>,
  Check2: (p) => <Icon {...p} d={<><circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/></>}/>,
};

/* ============ Button ============ */
function Btn({ children, variant = "default", size = "md", icon, iconRight, onClick, disabled, className = "", style, type = "button", title }) {
  const cls = `btn ${variant === "primary" ? "btn-primary" : variant === "ghost" ? "btn-ghost" : variant === "line" ? "btn-line" : ""} ${size === "sm" ? "btn-sm" : ""} ${className}`;
  return (
    <button type={type} className={cls} onClick={onClick} disabled={disabled} style={{
      ...(size === "sm" ? { padding: "8px 12px", fontSize: 13, minHeight: 36 } : null),
      opacity: disabled ? 0.5 : 1,
      pointerEvents: disabled ? "none" : "auto",
      ...style,
    }} title={title}>
      {icon}
      {children}
      {iconRight}
    </button>
  );
}

/* ============ Chip ============ */
function Chip({ children, tone = "default", icon, onRemove }) {
  const cls = tone === "gold" ? "chip chip-gold"
    : tone === "wine" ? "chip chip-wine"
    : tone === "emerald" ? "chip chip-emerald"
    : tone === "outline" ? "chip chip-outline"
    : "chip";
  return (
    <span className={cls}>
      {icon}
      {children}
      {onRemove && (
        <button onClick={onRemove} style={{
          background: "transparent", border: 0, padding: 0, marginLeft: 2,
          color: "inherit", opacity: 0.6, display: "inline-flex",
        }}>
          <Icons.X size={12} />
        </button>
      )}
    </span>
  );
}

/* ============ Toggle ============ */
function Toggle({ value, onChange, label, hint }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "8px 0" }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500 }}>{label}</div>
        {hint && <div className="fg-dim" style={{ fontSize: 12, marginTop: 2, lineHeight: 1.4 }}>{hint}</div>}
      </div>
      <div className={`toggle ${value ? "on" : ""}`} onClick={() => onChange(!value)} role="switch" aria-checked={value} />
    </div>
  );
}

/* ============ Input field ============ */
function Field({ label, hint, children, optional }) {
  return (
    <label style={{ display: "block", marginBottom: 14 }}>
      <span className="field-label" style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
        <span>{label}</span>
        {optional && <span style={{ textTransform: "none", fontFamily: "var(--font-sans)", letterSpacing: 0, color: "var(--fg-dim)" }}>ไม่บังคับ</span>}
      </span>
      {children}
      {hint && <span className="fg-dim" style={{ fontSize: 12, marginTop: 6, display: "block", lineHeight: 1.4 }}>{hint}</span>}
    </label>
  );
}

/* ============ Modal ============ */
function Modal({ open, onClose, title, children, actions }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 className="display" style={{ margin: 0, fontSize: 22 }}>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="ปิด">
            <Icons.X size={18} />
          </button>
        </div>
        {children}
        {actions && (
          <div style={{ display: "flex", gap: 10, marginTop: 18, flexDirection: "column" }}>
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}

/* ============ Sebastian Message — formal butler note ============ */
function ButlerNote({ children, tone = "default" }) {
  return (
    <div className="surface-card" style={{
      padding: "14px 16px",
      background: tone === "gold" ? "var(--gold-glow)" : "var(--surface)",
      border: `1px solid ${tone === "gold" ? "var(--accent-deep)" : "var(--border)"}`,
      borderRadius: "var(--r-lg)",
      display: "flex",
      gap: 12,
      alignItems: "flex-start",
    }}>
      <div style={{ flexShrink: 0, color: "var(--accent)", marginTop: 2 }}>
        <Crest size={28} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="serif" style={{ fontSize: 14.5, lineHeight: 1.55, fontStyle: "italic" }}>
          {children}
        </div>
        <div className="mono" style={{ fontSize: 10, marginTop: 6, color: "var(--fg-dim)", letterSpacing: "0.08em" }}>
          — Sebastian
        </div>
      </div>
    </div>
  );
}

/* ============ TopBar with monogram ============ */
function TopBar({ title, subtitle, leftIcon, onLeft, rightIcon, onRight, right }) {
  return (
    <div className="topbar">
      <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0, flex: 1 }}>
        {leftIcon ? (
          <button className="icon-btn" onClick={onLeft}>{leftIcon}</button>
        ) : (
          <div style={{ color: "var(--accent)", flexShrink: 0 }}>
            <Crest size={28} />
          </div>
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="display" style={{ fontSize: 18, lineHeight: 1.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{title}</div>
          {subtitle && <div className="fg-dim" style={{ fontSize: 11, fontFamily: "var(--font-mono)", letterSpacing: "0.04em", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{subtitle}</div>}
        </div>
      </div>
      {right ? right : (rightIcon ? (
        <button className="icon-btn" onClick={onRight}>{rightIcon}</button>
      ) : null)}
    </div>
  );
}

// Export globally
Object.assign(window, {
  Crest, Fleur, Diamond, DividerOrnate, Icons,
  Btn, Chip, Toggle, Field, Modal, ButlerNote, TopBar,
});
