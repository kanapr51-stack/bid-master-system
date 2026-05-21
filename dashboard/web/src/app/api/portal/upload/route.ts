import { NextRequest, NextResponse } from 'next/server';
import { parseSessionCookie, COOKIE_NAME } from '@/lib/session';

const MAX_SIZE = 10 * 1024 * 1024;

export async function POST(req: NextRequest) {
  const sessionValue = req.cookies.get(COOKIE_NAME)?.value;
  if (!sessionValue) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  const session = await parseSessionCookie(sessionValue);
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  let formData: FormData;
  try { formData = await req.formData(); }
  catch { return NextResponse.json({ error: 'Invalid form data' }, { status: 400 }); }

  const file = formData.get('file') as File | null;
  const companyId = formData.get('companyId') as string | null;

  if (!file || !companyId) return NextResponse.json({ error: 'Missing file or companyId' }, { status: 400 });
  if (file.size > MAX_SIZE) return NextResponse.json({ error: 'ไฟล์ใหญ่เกิน 10MB' }, { status: 413 });

  // Vercel Blob — requires BLOB_READ_WRITE_TOKEN in env
  const blobToken = process.env.BLOB_READ_WRITE_TOKEN;
  if (!blobToken) {
    // Fallback: return metadata only (file not persisted — notify user)
    return NextResponse.json({
      url: '',
      name: file.name,
      sizeBytes: file.size,
      warning: 'BLOB_READ_WRITE_TOKEN not configured — file not saved',
    });
  }

  try {
    const { put } = await import('@vercel/blob');
    const blob = await put(
      `portal/${session.lineUserId}/${companyId}/${Date.now()}_${file.name}`,
      file,
      { access: 'public', token: blobToken },
    );
    return NextResponse.json({ url: blob.url, name: file.name, sizeBytes: file.size });
  } catch (err) {
    console.error('[upload]', err);
    return NextResponse.json({ error: 'Upload failed' }, { status: 500 });
  }
}
