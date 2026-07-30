import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';
import { requireOnboarding } from '@/lib/onboarding';
import { parsePortalNotes } from '@/lib/portal-data';
import { DocumentsClient } from './_client';

export const dynamic = 'force-dynamic';

export default async function DocumentsPage() {
  const cookieStore = await cookies();
  const sessionValue = cookieStore.get(COOKIE_NAME)?.value;
  if (!sessionValue) redirect('/portal/login');

  const session = await parseSessionCookie(sessionValue);
  if (!session) redirect('/portal/login');

  const customer = await requireOnboarding(session.lineUserId);

  const notes = parsePortalNotes(customer?.notes ?? '');

  return (
    <DocumentsClient
      lineUserId={session.lineUserId}
      classes={notes.classes ?? []}
      initialDocuments={notes.documents ?? {}}
    />
  );
}
