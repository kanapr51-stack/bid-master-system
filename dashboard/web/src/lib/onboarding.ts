/**
 * Onboarding gate: profile → settings → notifications ต้องผ่านตามลำดับก่อนใช้งาน /portal อื่นได้
 * spec: docs/superpowers/specs/2026-07-30-portal-onboarding-flow-design.md
 */
import { redirect } from 'next/navigation';
import { getCustomerByLineId, type Customer } from './customers';
import { parsePortalNotes } from './portal-data';

export function nextOnboardingPath(customer: Customer | null): string | null {
  const notes = parsePortalNotes(customer?.notes ?? '');

  if (!notes.userName?.trim() || !notes.userGmail?.trim()
    || !notes.userPhone?.trim() || !notes.userLineId?.trim()) {
    return '/portal/profile';
  }
  if (!notes.settingsConfirmedAt) {
    return '/portal/settings';
  }
  if (!customer?.has_push_subscription && !notes.notificationsPromptDismissedAt) {
    return '/portal/notifications';
  }
  return null;
}

/** เรียกจากหน้าใช้งานทั่วไป (world, jobs, ...) — fetch customer แล้ว redirect ถ้ายังไม่ผ่าน onboarding */
export async function requireOnboarding(lineUserId: string): Promise<Customer | null> {
  let customer: Customer | null = null;
  try {
    customer = await getCustomerByLineId(lineUserId);
  } catch {
    return null; // engine ล่ม — fail-open ปล่อยเข้า (ไม่ให้ onboarding gate เป็นจุดเดียวที่พังแล้วเข้าไม่ได้เลย)
  }
  const next = nextOnboardingPath(customer);
  if (next) redirect(next);
  return customer;
}
