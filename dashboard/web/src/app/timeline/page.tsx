import { readSnapshot } from "@/lib/snapshot";
import { HeaderBar } from "@/components/HeaderBar";
import { InflectionList } from "@/components/InflectionList";

export const dynamic = "force-dynamic";

export default async function TimelinePage() {
  const snapshot = await readSnapshot();

  return (
    <>
      <HeaderBar generatedAt={snapshot.generated_at} />
      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            📜 Inflection Timeline
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            จุดเปลี่ยน (commits) พร้อม metrics ก่อน/หลัง · เทียบผลกระทบจริงของแต่ละการเปลี่ยนแปลง
          </p>
        </div>

        <div className="flex gap-3 text-xs text-slate-500 dark:text-slate-400">
          <span>📊 {snapshot.inflections.length} inflection points</span>
          <span>·</span>
          <span>{snapshot.commits.length} commits ทั้งหมด</span>
        </div>

        <InflectionList inflections={snapshot.inflections} />
      </main>
    </>
  );
}
