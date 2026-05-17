import { NextResponse, type NextRequest } from "next/server";

const AUTH_REALM = "Bid Master Dashboard";

function unauthorized() {
  return new NextResponse("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": `Basic realm="${AUTH_REALM}", charset="UTF-8"`,
    },
  });
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

export function middleware(req: NextRequest) {
  const expectedUser = process.env.DASHBOARD_USER;
  const expectedPass = process.env.DASHBOARD_PASS;

  // If auth env not configured, skip auth (dev mode)
  if (!expectedUser || !expectedPass) {
    return NextResponse.next();
  }

  const header = req.headers.get("authorization") ?? "";
  if (!header.startsWith("Basic ")) {
    return unauthorized();
  }

  try {
    const encoded = header.slice(6).trim();
    const decoded = atob(encoded);
    const idx = decoded.indexOf(":");
    if (idx < 0) return unauthorized();
    const user = decoded.slice(0, idx);
    const pass = decoded.slice(idx + 1);

    if (!timingSafeEqual(user, expectedUser) || !timingSafeEqual(pass, expectedPass)) {
      return unauthorized();
    }
    return NextResponse.next();
  } catch {
    return unauthorized();
  }
}

// Apply auth to all routes EXCEPT:
//   - /api/snapshot, /api/revalidate (use x-revalidate-secret header instead)
//   - _next/static, _next/image, favicon.ico (static assets)
export const config = {
  matcher: ["/((?!api/snapshot|api/revalidate|_next/static|_next/image|favicon.ico).*)"],
};
