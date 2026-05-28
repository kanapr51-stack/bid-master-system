/**
 * LINE Login OAuth — initiation endpoint
 * GET /api/auth/line → redirect to LINE OAuth
 */
import { NextRequest, NextResponse } from 'next/server';

export async function GET(req: NextRequest) {
  const channelId = process.env.LINE_LOGIN_CHANNEL_ID;
  const redirectUri = getRedirectUri(req);

  if (!channelId) {
    // Dev mode: skip LINE OAuth, create mock session
    return NextResponse.redirect(new URL('/api/auth/line/callback?mock=1', req.url));
  }

  const state = crypto.randomUUID();
  const url = new URL('https://access.line.me/oauth2/v2.1/authorize');
  url.searchParams.set('response_type', 'code');
  url.searchParams.set('client_id', channelId);
  url.searchParams.set('redirect_uri', redirectUri);
  url.searchParams.set('state', state);
  url.searchParams.set('scope', 'profile openid');

  const res = NextResponse.redirect(url.toString());
  res.cookies.set('line_oauth_state', state, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    maxAge: 600,
    path: '/',
  });
  return res;
}

function getRedirectUri(req: NextRequest): string {
  if (process.env.LINE_LOGIN_REDIRECT_URI) return process.env.LINE_LOGIN_REDIRECT_URI;
  const url = new URL(req.url);
  return `${url.protocol}//${url.host}/api/auth/line/callback`;
}
