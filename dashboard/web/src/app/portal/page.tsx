import { redirect } from 'next/navigation';
import { cookies } from 'next/headers';
import { COOKIE_NAME } from '@/lib/session';

export default async function PortalRootPage() {
  const cookieStore = await cookies();
  const session = cookieStore.get(COOKIE_NAME);
  redirect(session?.value ? '/portal/world' : '/portal/login');
}
