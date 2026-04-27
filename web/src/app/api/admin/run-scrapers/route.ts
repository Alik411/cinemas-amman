import { NextRequest, NextResponse } from 'next/server'
import { exec } from 'child_process'
import path from 'path'

export async function POST(req: NextRequest) {
  const password = req.headers.get('x-admin-password')
  if (password !== process.env.ADMIN_PASSWORD) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  // NOTE: This only works when self-hosted (not on Vercel free tier).
  // On Vercel, serverless functions cannot spawn long-running processes.
  const scraperDir = path.join(process.cwd(), '..', 'scraper')
  const venvPython = path.join(scraperDir, 'venv', 'Scripts', 'python.exe')
  const mainScript = path.join(scraperDir, 'main.py')

  return new Promise<NextResponse>(resolve => {
    exec(`"${venvPython}" "${mainScript}"`, { cwd: scraperDir, timeout: 120_000 }, (err, stdout, stderr) => {
      if (err) {
        resolve(NextResponse.json({ success: false, error: err.message, stderr }, { status: 500 }))
      } else {
        resolve(NextResponse.json({ success: true, output: stdout }))
      }
    })
  })
}
