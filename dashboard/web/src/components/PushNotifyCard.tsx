"use client";
/**
 * การ์ด 🔔 เปิดรับแจ้งเตือน browser (Web Push) — spec 2026-07-13-web-push-notification-design.md
 * สถานะ: unsupported→ซ่อน · iOS ยังไม่ standalone→สอน Add to Home Screen ·
 * ยังไม่เปิด→ปุ่มเปิด · เปิดแล้ว→✅ + ส่งทดสอบ + ปิด
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

export default function PushNotifyCard() {
  const [state, setState] = useState<State>("loading");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    (async () => {
      if (!("serviceWorker" in navigator) || !("PushManager" in window) || !VAPID_PUBLIC) {
        // iOS Safari ที่ยังไม่ Add to Home Screen จะไม่มี PushManager
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

  const sendTest = useCallback(async () => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch("/api/portal/push/test", { method: "POST" });
      const data = await r.json();
      setMsg(data.ok && data.sent > 0
        ? `ส่งทดสอบแล้ว ${data.sent} เครื่อง — ควรเด้งภายในไม่กี่วินาที`
        : "ส่งไม่สำเร็จ — ลองปิดแล้วเปิดแจ้งเตือนใหม่");
    } catch {
      setMsg("ส่งไม่สำเร็จ — เชื่อมต่อไม่ได้");
    } finally { setBusy(false); }
  }, []);

  if (state === "loading" || state === "unsupported") return null;

  return (
    <div className="p-card" style={{ padding: 14, marginBottom: 14, display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--accent)" }}>
        <Icons.Bell size={16} />
        <span className="p-display" style={{ fontSize: 15 }}>แจ้งเตือนผ่านเบราว์เซอร์</span>
      </div>
      {state === "ios-install" && (
        <p className="p-fg-mute" style={{ margin: "4px 0 0", fontSize: 13, lineHeight: 1.5 }}>
          iPhone/iPad: กดปุ่มแชร์ แล้วเลือก &quot;เพิ่มไปยังหน้าจอโฮม&quot; ก่อน
          จากนั้นเปิดจากไอคอนบนหน้าจอโฮมเพื่อเปิดรับแจ้งเตือน
        </p>
      )}
      {state === "denied" && (
        <p className="p-fg-mute" style={{ margin: "4px 0 0", fontSize: 13, lineHeight: 1.5 }}>
          เบราว์เซอร์นี้ถูกตั้งค่าบล็อกแจ้งเตือนไว้ — ไปที่ตั้งค่าเว็บไซต์ของเบราว์เซอร์
          แล้วอนุญาตการแจ้งเตือน จากนั้นรีเฟรชหน้านี้
        </p>
      )}
      {state === "off" && (
        <button className="p-btn p-btn-primary" onClick={enable} disabled={busy}
          style={{ marginTop: 6, height: 34, padding: "0 16px", fontSize: 13, alignSelf: "flex-start" }}>
          {busy ? "กำลังเปิด…" : "เปิดรับแจ้งเตือนเครื่องนี้"}
        </button>
      )}
      {state === "on" && (
        <div style={{ marginTop: 6, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span className="p-fg-mute" style={{ fontSize: 13 }}>✅ เครื่องนี้รับแจ้งเตือนอยู่</span>
          <button className="p-btn p-btn-ghost" onClick={sendTest} disabled={busy}
            style={{ height: 30, padding: "0 12px", fontSize: 12.5 }}>ส่งทดสอบ</button>
          <button className="p-btn p-btn-ghost" onClick={disable} disabled={busy}
            style={{ height: 30, padding: "0 12px", fontSize: 12.5 }}>ปิด</button>
        </div>
      )}
      {msg && <p className="p-fg-dim" style={{ margin: "4px 0 0", fontSize: 12.5 }}>{msg}</p>}
    </div>
  );
}
