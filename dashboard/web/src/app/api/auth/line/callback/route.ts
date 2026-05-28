/**
 * LINE Login OAuth — callback endpoint
 * GET /api/auth/line/callback?code=xxx&state=xxx
 */
import { NextRequest, NextResponse } from 'next/server';
import { createSessionCookie, COOKIE_NAME, MAX_AGE_SECONDS } from '@/lib/session';
import { upsertCustomer } from '@/lib/customers';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);

  // Dev mode: no LINE credentials configured
  if (searchParams.get('mock') === '1') {
    return createMockSession(req);
  }

  const code = searchParams.get('code');
  const state = searchParams.get('state');
  const storedState = req.cookies.get('line_oauth_state')?.value;

  if (!code || !state || state !== storedState) {
    return NextResponse.redirect(new URL('/portal/login?error=invalid_state', req.url));
  }

  try {
    const channelId = process.env.LINE_LOGIN_CHANNEL_ID!;
    const channelSecret = process.env.LINE_LOGIN_CHANNEL_SECRET!;
    const redirectUri = getRedirectUri(req);

    // Exchange code for token
    const tokenRes = await fetch('https://api.line.me/oauth2/v2.1/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'authorization_code',
        code,
        redirect_uri: redirectUri,
        client_id: channelId,
        client_secret: channelSecret,
      }),
    });
    if (!tokenRes.ok) throw new Error('Token exchange failed');
    const { access_token } = await tokenRes.json() as { access_token: string };

    // Get user profile
    const profileRes = await fetch('https://api.line.me/v2/profile', {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    if (!profileRes.ok) throw new Error('Profile fetch failed');
    const profile = await profileRes.json() as { userId: string; displayName: string; pictureUrl?: string };

    return finishLogin(req, profile.userId, profile.displayName, profile.pictureUrl);
  } catch (err) {
    console.error('[LINE callback]', err);
    return NextResponse.redirect(new URL('/portal/login?error=auth_failed', req.url));
  }
}

async function createMockSession(req: NextRequest) {
  return finishLogin(req, 'dev-mock-user-001', 'Dev User (Mock)', undefined);
}

async function finishLogin(req: NextRequest, lineUserId: string, displayName: string, pictureUrl?: string) {
  // Ensure customer exists in Sheets
  try {
    await upsertCustomer({ line_user_id: lineUserId, display_name: displayName });
  } catch (err) {
    // Non-fatal: log but continue
    console.warn('[finishLogin] upsertCustomer failed:', err);
  }

  const cookie = await createSessionCookie({ lineUserId, displayName, pictureUrl });
  const res = NextResponse.redirect(new URL('/portal/world', req.url));

  res.cookies.set(COOKIE_NAME, cookie, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    maxAge: MAX_AGE_SECONDS,
    path: '/',
  });

  // Clear state cookie
  res.cookies.delete('line_oauth_state');
  return res;
}

function getRedirectUri(req: NextRequest): string {
  if (process.env.LINE_LOGIN_REDIRECT_URI) return process.env.LINE_LOGIN_REDIRECT_URI;
  const url = new URL(req.url);
  return `${url.protocol}//${url.host}/api/auth/line/callback`;
}
