"use client";

import { useState, useTransition } from "react";
import { Save, Check, AlertCircle } from "lucide-react";
import type { Customer } from "@/lib/customers";

const PROVINCES = [
  "นครพนม", "บึงกาฬ", "หนองคาย", "สกลนคร", "มุกดาหาร",
  "อุดรธานี", "หนองบัวลำภู", "เลย", "ขอนแก่น", "ร้อยเอ็ด",
  "กาฬสินธุ์", "มหาสารคาม", "ชัยภูมิ", "อุบลราชธานี",
  "ยโสธร", "อำนาจเจริญ", "นครราชสีมา", "บุรีรัมย์",
  "สุรินทร์", "ศรีสะเกษ",
];

interface Props {
  lineUserId: string;
  initial: Customer | null;
}

function splitCsv(v: string): string[] {
  return v.split(",").map((s) => s.trim()).filter(Boolean);
}

export function CustomerForm({ lineUserId, initial }: Props) {
  const [displayName, setDisplayName] = useState(initial?.display_name ?? "");
  const [phone, setPhone] = useState(initial?.phone ?? "");
  const [email, setEmail] = useState(initial?.email ?? "");
  const [provinces, setProvinces] = useState<string[]>(
    splitCsv(initial?.จังหวัด ?? ""),
  );
  const [districts, setDistricts] = useState(initial?.อำเภอ ?? "");
  const [keywords, setKeywords] = useState(initial?.keywords ?? "");
  const [isPending, startTransition] = useTransition();
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const toggleProvince = (p: string) => {
    setProvinces((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p],
    );
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setStatus("idle");
    setErrorMsg("");
    startTransition(async () => {
      try {
        const res = await fetch("/api/line/customer", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            line_user_id: lineUserId,
            display_name: displayName.trim(),
            phone: phone.trim(),
            email: email.trim(),
            จังหวัด: provinces.join(", "),
            อำเภอ: districts.trim(),
            keywords: keywords.trim(),
          }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error ?? "save failed");
        setStatus("saved");
        setTimeout(() => setStatus("idle"), 3000);
      } catch (e) {
        setStatus("error");
        setErrorMsg(e instanceof Error ? e.message : String(e));
      }
    });
  };

  return (
    <form onSubmit={onSubmit} className="space-y-5">
      {/* Display name */}
      <div>
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
          ชื่อแสดง <span className="text-rose-500">*</span>
        </label>
        <input
          type="text"
          required
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="ชื่อหรือชื่อบริษัท"
          className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 dark:text-slate-100"
        />
      </div>

      {/* Provinces (multi-select chips) */}
      <div>
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
          จังหวัด <span className="text-rose-500">*</span>{" "}
          <span className="text-xs text-slate-500 font-normal">
            (เลือกได้หลายจังหวัด — แตะเพื่อเปิด/ปิด)
          </span>
        </label>
        <div className="flex flex-wrap gap-1.5">
          {PROVINCES.map((p) => {
            const active = provinces.includes(p);
            return (
              <button
                key={p}
                type="button"
                onClick={() => toggleProvince(p)}
                className={
                  "px-3 py-1 text-xs font-medium rounded-md transition " +
                  (active
                    ? "bg-blue-600 text-white"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700")
                }
              >
                {p}
              </button>
            );
          })}
        </div>
        {provinces.length === 0 && (
          <p className="text-xs text-amber-600 dark:text-amber-400 mt-2">
            ⚠ ยังไม่ได้เลือกจังหวัด — เลือกอย่างน้อย 1 จังหวัด
          </p>
        )}
      </div>

      {/* Districts */}
      <div>
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
          อำเภอ{" "}
          <span className="text-xs text-slate-500 font-normal">
            (คั่นด้วย comma — เช่น &quot;บ้านแพง, บึงโขงหลง&quot;)
          </span>
        </label>
        <input
          type="text"
          value={districts}
          onChange={(e) => setDistricts(e.target.value)}
          placeholder="ไม่ระบุ = ทุกอำเภอในจังหวัด"
          className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 dark:text-slate-100"
        />
      </div>

      {/* Keywords */}
      <div>
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
          Keywords เพิ่มเติม{" "}
          <span className="text-xs text-slate-500 font-normal">
            (เพิ่ม keyword ที่อยากให้กรอง — เช่น &quot;ก่อสร้าง, ถนน&quot;)
          </span>
        </label>
        <input
          type="text"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          placeholder="ไม่ระบุ = ใช้ default keywords (ถนน, สะพาน, อาคาร, ฯลฯ)"
          className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 dark:text-slate-100"
        />
      </div>

      {/* Contact (optional) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
            เบอร์โทร{" "}
            <span className="text-xs text-slate-500 font-normal">(optional)</span>
          </label>
          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="0xx-xxx-xxxx"
            className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 dark:text-slate-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
            Email <span className="text-xs text-slate-500 font-normal">(optional)</span>
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-slate-900 dark:text-slate-100"
          />
        </div>
      </div>

      {/* Submit */}
      <div className="pt-2">
        <button
          type="submit"
          disabled={isPending || !displayName.trim() || provinces.length === 0}
          className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium rounded-md transition"
        >
          {isPending ? (
            "กำลังบันทึก..."
          ) : status === "saved" ? (
            <>
              <Check className="size-4" />
              บันทึกแล้ว — Sebastian จะส่งแจ้งเตือนตามการตั้งค่านี้
            </>
          ) : (
            <>
              <Save className="size-4" />
              บันทึกการตั้งค่า
            </>
          )}
        </button>
        {status === "error" && (
          <p className="mt-2 text-sm text-rose-600 dark:text-rose-400 flex items-center gap-1">
            <AlertCircle className="size-4" />
            {errorMsg}
          </p>
        )}
      </div>
    </form>
  );
}
