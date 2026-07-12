import { redirect } from 'next/navigation';

// N+199: ระบบบริษัทถูกถอด — ลิงก์เก่าทั้งหมดเด้งไปหน้าตั้งค่าแบน
export default function ClassesPage() {
  redirect('/portal/settings');
}
