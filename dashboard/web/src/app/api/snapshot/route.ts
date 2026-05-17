import { put, list, del } from "@vercel/blob";
import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SNAPSHOT_KEY = "snapshot.json";
const PATHS_TO_REVALIDATE = ["/", "/scrape", "/classifier", "/funnel", "/timeline", "/history"];

/**
 * POST /api/snapshot
 * Header: x-revalidate-secret: <REVALIDATE_SECRET>
 * Body: full snapshot JSON
 *
 * Uploads the snapshot to Vercel Blob with a stable name (overwrites previous),
 * then revalidates all dashboard pages so they pick up the new data on next render.
 */
export async function POST(req: Request) {
  const secret = req.headers.get("x-revalidate-secret");
  const expected = process.env.REVALIDATE_SECRET;

  if (!expected) {
    return NextResponse.json(
      { ok: false, error: "REVALIDATE_SECRET not configured" },
      { status: 500 },
    );
  }
  if (secret !== expected) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  let raw: string;
  try {
    raw = await req.text();
    JSON.parse(raw);
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: "invalid JSON body", detail: String(e) },
      { status: 400 },
    );
  }

  // Delete the previous snapshot blobs (since put() with allowOverwrite would
  // still let stale historical files accumulate)
  try {
    const existing = await list({ prefix: "snapshot" });
    if (existing.blobs.length > 0) {
      await del(existing.blobs.map((b) => b.url));
    }
  } catch {
    // non-fatal — proceed to put
  }

  const blob = await put(SNAPSHOT_KEY, raw, {
    access: "public",
    contentType: "application/json",
    addRandomSuffix: false,
    allowOverwrite: true,
    cacheControlMaxAge: 0,
  });

  for (const p of PATHS_TO_REVALIDATE) revalidatePath(p);

  return NextResponse.json({
    ok: true,
    blob: { url: blob.url, pathname: blob.pathname, size: raw.length },
    revalidated: PATHS_TO_REVALIDATE,
    at: new Date().toISOString(),
  });
}

export async function GET() {
  // Returns the latest blob URL (handy for debugging)
  const { blobs } = await list({ prefix: "snapshot" });
  return NextResponse.json({
    ok: true,
    count: blobs.length,
    blobs: blobs.map((b) => ({
      pathname: b.pathname,
      url: b.url,
      size: b.size,
      uploadedAt: b.uploadedAt,
    })),
  });
}
