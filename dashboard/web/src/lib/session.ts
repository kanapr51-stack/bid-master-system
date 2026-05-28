/**
 * session.ts — HMAC-SHA256 signed cookie session
 * No external dependencies — uses Web Crypto API
 */

export const COOKIE_NAME = 'portal_session';
export const MAX_AGE_SECONDS = 60 * 60 * 24 * 30; // 30 days

export interface Session {
  lineUserId: string;
  displayName: string;
  pictureUrl?: string;
}

function getSecret(): string {
  return process.env.SESSION_SECRET ?? 'dev-secret-please-change-in-production';
}

async function hmac(data: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(data));
  // URL-safe base64
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export async function createSessionCookie(session: Session): Promise<string> {
  const payload = btoa(JSON.stringify(session))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const sig = await hmac(payload, getSecret());
  return `${payload}.${sig}`;
}

export async function parseSessionCookie(value: string): Promise<Session | null> {
  try {
    const dot = value.lastIndexOf('.');
    if (dot < 0) return null;
    const payload = value.slice(0, dot);
    const sig = value.slice(dot + 1);
    const expected = await hmac(payload, getSecret());
    if (expected !== sig) return null;
    // Restore base64 padding
    const padded = payload.replace(/-/g, '+').replace(/_/g, '/') + '=='.slice((payload.length % 4) || 4);
    return JSON.parse(atob(padded)) as Session;
  } catch {
    return null;
  }
}
