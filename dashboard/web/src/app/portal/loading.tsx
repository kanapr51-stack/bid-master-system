// app/portal/loading.tsx — Suspense fallback ของทุกหน้าใน /portal/* (Next.js App Router
// แสดงอัตโนมัติทันทีที่กด Link ระหว่างรอหน้าใหม่ทำงานฝั่ง server เสร็จ — เดิมไม่มี loading.tsx
// เลยกดแล้ว "เหมือนไม่ตอบสนอง" จนกว่าทั้งหน้าจะโหลดเสร็จ N+226.4)
export default function PortalLoading() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 12, minHeight: '60dvh',
    }}>
      <div className="p-spinner" />
    </div>
  );
}
