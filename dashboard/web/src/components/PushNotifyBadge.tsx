"use client";
/**
 * ไอคอนสถานะแจ้งเตือน browser (Web Push) แบบเล็ก — ใช้แทนการ์ดใหญ่เดิม
 * (PushNotifyCard.tsx เดิม, N+218 ย่อเป็นไอคอนข้าง title)
 * สถานะ: unsupported→ซ่อน · off→ไอคอนจาง กดเพื่อเปิด · on→ไอคอนเน้นสี กดเพื่อปิด ·
 * ios-install/denied→ไอคอนจาง กดเพื่อดูข้อความอธิบายสั้นๆ
 */
import { useCallback, useEffect, useState } from "react";
import { Icons } from "@/app/portal/_ui";

const VAPID_PUBLIC = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY ?? "";

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

type State = "loading" | "unsupported" | "ios-install" | "off" | "on" | "denied";

const EXPLAIN: Record<string, string> = {
  "ios-install": "iPhone/iPad: กดปุ่มแชร์ แล้วเลือก \"เพิ่มไปยังหน้าจอโฮม\" ก่อน จากนั้นเปิดจากไอคอนบนหน้าจอโฮมเพื่อเปิดรับแจ้งเตือน",
  denied: "เบราว์เซอร์นี้ถูกตั้งค่าบล็อกแจ้งเตือนไว้ — ไปที่ตั้งค่าเว็บไซต์ของเบราว์เซอร์แล้วอนุญาตการแจ้งเตือน จากนั้นรีเฟรชหน้านี้",
};

export default function PushNotifyBadge() {
  const [state, setState] = useState<State>("loading");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    (async () => {
      if (!("serviceWorker" in navigator) || !("PushManager" in window) || !VAPID_PUBLIC) {
        const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        const standalone = window.matchMedia("(display-mode: standalone)").matches
          || (navigator as unknown as { standalone?: boolean }).standalone === true;
        setState(isIOS && !standalone ? "ios-install" : "unsupported");
        return;
      }
      if (Notification.permission === "denied") { setState("denied"); return; }
      const reg = await navigator.serviceWorker.register("/sw.js");
      const sub = await reg.pushManager.getSubscription();
      setState(sub ? "on" : "off");
    })().catch(() => setState("unsupported"));
  }, []);

  const enable = useCallback(async () => {
    setBusy(true); setMsg("");
    try {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { setState(perm === "denied" ? "denied" : "off"); return; }
      const reg = await navigator.serviceWorker.register("/sw.js");
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC) as BufferSource,
      });
      const json = sub.toJSON();
      const r = await fetch("/api/portal/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          endpoint: sub.endpoint,
          p256dh: json.keys?.p256dh ?? "",
          auth: json.keys?.auth ?? "",
          user_agent: navigator.userAgent,
        }),
      });
      if (r.status === 403) {
        await sub.unsubscribe();
        setState("off"); setMsg("ฟีเจอร์นี้ยังเปิดทดลองเฉพาะบางบัญชี");
        return;
      }
      if (!(await r.json()).ok) throw new Error("save failed");
      setState("on"); setMsg("เปิดรับแจ้งเตือนเครื่องนี้แล้ว ✅");
    } catch {
      setMsg("เปิดไม่สำเร็จ ลองใหม่อีกครั้ง");
    } finally { setBusy(false); }
  }, []);

  const disable = useCallback(async () => {
    setBusy(true); setMsg("");
    try {
      const reg = await navigator.serviceWorker.register("/sw.js");
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await fetch("/api/portal/push/unsubscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: sub.endpoint }),
        });
        await sub.unsubscribe();
      }
      setState("off"); setMsg("ปิดแจ้งเตือนเครื่องนี้แล้ว");
    } catch {
      setMsg("ปิดไม่สำเร็จ ลองใหม่อีกครั้ง");
    } finally { setBusy(false); }
  }, []);

  const onClick = useCallback(() => {
    if (busy) return;
    if (state === "off") { void enable(); return; }
    if (state === "on") { void disable(); return; }
    // ios-install / denied — ไม่มี action ทำได้ แค่โชว์/ซ่อนคำอธิบาย
    setMsg(prev => (prev ? "" : EXPLAIN[state] ?? ""));
  }, [state, busy, enable, disable]);

  if (state === "loading" || state === "unsupported") return null;

  const active = state === "on";
  const title = active ? "แจ้งเตือนเปิดอยู่ — กดเพื่อปิด"
    : state === "off" ? "กดเพื่อเปิดรับแจ้งเตือน"
    : "แตะเพื่อดูวิธีเปิดแจ้งเตือน";

  return (
    <span style={{ position: "relative", display: "inline-flex" }}>
      <button
        onClick={onClick}
        disabled={busy}
        title={title}
        aria-label={title}
        style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          width: 22, height: 22, padding: 0, border: "none", background: "none",
          cursor: busy ? "default" : "pointer",
          color: active ? "var(--accent)" : "var(--fg-dim)",
          opacity: busy ? 0.5 : 1,
        }}
      >
        <Icons.Bell size={15} sw={active ? 2 : 1.5} />
      </button>
      {msg && (
        <span className="p-fg-dim" style={{
          position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 20,
          width: 220, fontSize: 11.5, lineHeight: 1.5, background: "var(--surface)",
          border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px",
          boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
        }}>
          {msg}
        </span>
      )}
    </span>
  );
}
