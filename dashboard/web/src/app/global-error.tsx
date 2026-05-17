"use client";

import { useEffect } from "react";

interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    console.error("[dashboard] global error:", error);
  }, [error]);

  return (
    <html lang="th">
      <body
        style={{
          margin: 0,
          padding: 0,
          minHeight: "100vh",
          fontFamily: "system-ui, -apple-system, sans-serif",
          background: "#0f172a",
          color: "#f1f5f9",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div style={{ maxWidth: 500, padding: 32, textAlign: "center" }}>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>
            ระบบขัดข้องชั่วคราว
          </h1>
          <p style={{ marginTop: 12, color: "#94a3b8", fontSize: 14 }}>
            Dashboard layout เกิดข้อผิดพลาดที่ recover ไม่ได้
            {error.digest ? ` (${error.digest})` : ""}
          </p>
          <button
            onClick={reset}
            style={{
              marginTop: 24,
              padding: "10px 20px",
              background: "#3b82f6",
              color: "white",
              border: "none",
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            ลองใหม่
          </button>
        </div>
      </body>
    </html>
  );
}
