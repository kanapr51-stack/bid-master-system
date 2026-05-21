import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import HistoryClient from './_client';

export default async function HistoryPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');
  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  return <HistoryClient />;
}
