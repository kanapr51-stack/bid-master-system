import { getCustomerByLineId } from "@/lib/customers";
import { CustomerForm } from "@/components/CustomerForm";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ lineUserId: string }>;
}

export default async function CustomerSettingsPage({ params }: PageProps) {
  const { lineUserId } = await params;

  let customer = null;
  let loadError: string | null = null;
  try {
    customer = await getCustomerByLineId(lineUserId);
  } catch (e) {
    loadError = e instanceof Error ? e.message : String(e);
  }

  const isNew = !customer;

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-blue-50 dark:from-slate-950 dark:to-slate-900 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center gap-2 mb-3">
            <span className="text-3xl">🎩</span>
            <h1 className="text-3xl font-bold text-slate-900 dark:text-slate-100">
              Sebastian
            </h1>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            ระบบแจ้งเตือนงานประมูล eGP — ตั้งค่าได้ตามต้องการ
          </p>
        </div>

        {loadError ? (
          <div className="rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 p-6">
            <p className="text-rose-700 dark:text-rose-300 font-medium">โหลดข้อมูลไม่ได้</p>
            <p className="text-sm text-rose-600 dark:text-rose-400 mt-1">{loadError}</p>
          </div>
        ) : (
          <div className="rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm p-6 md:p-8">
            <div className="mb-6">
              {isNew ? (
                <>
                  <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
                    ยินดีต้อนรับ! 🎉
                  </h2>
                  <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                    เริ่มใช้ฟรี 14 วัน · ตั้งค่าจังหวัดและอำเภอที่ต้องการรับแจ้งเตือน
                  </p>
                </>
              ) : (
                <>
                  <h2 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
                    การตั้งค่าของคุณ
                  </h2>
                  <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
                    {customer!.display_name || "(ยังไม่ระบุชื่อ)"} ·{" "}
                    <span
                      className={
                        customer!.status === "active"
                          ? "text-emerald-600 dark:text-emerald-400 font-medium"
                          : customer!.status === "trial"
                          ? "text-amber-600 dark:text-amber-400 font-medium"
                          : "text-rose-600 dark:text-rose-400 font-medium"
                      }
                    >
                      {customer!.status === "active"
                        ? "🟢 Active"
                        : customer!.status === "trial"
                        ? "🟡 Trial"
                        : `🔴 ${customer!.status}`}
                    </span>
                    {customer!.expires_at && ` · หมดอายุ ${customer!.expires_at.slice(0, 10)}`}
                  </p>
                </>
              )}
            </div>

            <CustomerForm lineUserId={lineUserId} initial={customer} />
          </div>
        )}

        <p className="mt-6 text-xs text-center text-slate-500 dark:text-slate-400">
          Bid Master System · ดูแลโดยคุณกัญจน์ · Powered by Sebastian
        </p>
      </div>
    </main>
  );
}
