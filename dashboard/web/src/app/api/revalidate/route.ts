import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/revalidate
 * Header: x-revalidate-secret: <REVALIDATE_SECRET>
 * Body (optional JSON): { path?: string }   // default "/"
 *
 * Triggers an on-demand revalidation of the page so dashboards pick up
 * a fresh snapshot.json without waiting for the next deploy.
 */
export async function POST(req: Request) {
  const secret = req.headers.get("x-revalidate-secret");
  const expected = process.env.REVALIDATE_SECRET;

  if (!expected) {
    return NextResponse.json(
      { ok: false, error: "REVALIDATE_SECRET not configured on server" },
      { status: 500 },
    );
  }

  if (secret !== expected) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  let path = "/";
  try {
    const body = (await req.json()) as { path?: string };
    if (typeof body.path === "string" && body.path.startsWith("/")) {
      path = body.path;
    }
  } catch {
    // empty body is fine
  }

  const paths = path === "/" ? ["/", "/scrape", "/classifier", "/funnel", "/timeline", "/history"] : [path];
  for (const p of paths) revalidatePath(p);

  return NextResponse.json({
    ok: true,
    revalidated: paths,
    at: new Date().toISOString(),
  });
}

export async function GET() {
  return NextResponse.json({
    ok: true,
    hint: "POST with header 'x-revalidate-secret' to trigger revalidation",
  });
}
