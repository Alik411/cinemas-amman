'use client'

import { useState } from 'react'
import type { ScraperLog, Cinema } from '@/types/database'
import { Film, Clock, CheckCircle, XCircle, AlertCircle, Play } from 'lucide-react'

interface Props {
  logs: (ScraperLog & { cinemas?: any })[]
  cinemas: Cinema[]
  movieCount: number
  showtimeCount: number
}

const PASSWORD_KEY = 'admin_password'

export default function AdminClient({ logs, cinemas, movieCount, showtimeCount }: Props) {
  const [password, setPassword] = useState('')
  const [authed, setAuthed] = useState(false)
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState<string | null>(null)

  function login(e: React.FormEvent) {
    e.preventDefault()
    setAuthed(true)
  }

  async function runScrapers() {
    setRunning(true)
    setRunResult(null)
    try {
      const res = await fetch('/api/admin/run-scrapers', {
        method: 'POST',
        headers: { 'x-admin-password': password },
      })
      const data = await res.json()
      setRunResult(data.success ? '✓ Scrapers completed' : `✗ Error: ${data.error}`)
    } catch {
      setRunResult('✗ Request failed')
    } finally {
      setRunning(false)
    }
  }

  if (!authed) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4">
        <form onSubmit={login} className="bg-zinc-900 border border-zinc-800 rounded-xl p-8 w-full max-w-sm">
          <h1 className="text-white font-bold text-xl mb-6">Admin Dashboard</h1>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Admin password"
            className="w-full bg-zinc-800 border border-zinc-700 text-white rounded-lg px-4 py-2.5 mb-4 focus:outline-none focus:border-amber-500"
          />
          <button type="submit" className="w-full bg-amber-500 hover:bg-amber-400 text-black font-semibold rounded-lg py-2.5 transition-colors">
            Login
          </button>
        </form>
      </div>
    )
  }

  const StatusIcon = ({ status }: { status: string }) => {
    if (status === 'success') return <CheckCircle size={14} className="text-green-400" />
    if (status === 'failed') return <XCircle size={14} className="text-red-400" />
    return <AlertCircle size={14} className="text-yellow-400" />
  }

  // Last run per cinema
  const lastRunByCinema = cinemas.map(c => {
    const last = logs.find(l => l.cinema_id === c.id)
    return { cinema: c, log: last }
  })

  return (
    <div className="min-h-screen bg-zinc-950 text-white p-4 md:p-8">
      <h1 className="text-2xl font-bold mb-8">Admin Dashboard</h1>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: 'Total Movies', value: movieCount, icon: Film },
          { label: 'Total Showtimes', value: showtimeCount, icon: Clock },
          { label: 'Active Cinemas', value: cinemas.filter(c => c.active).length, icon: CheckCircle },
          { label: 'Inactive Cinemas', value: cinemas.filter(c => !c.active).length, icon: XCircle },
        ].map(({ label, value, icon: Icon }) => (
          <div key={label} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <Icon size={18} className="text-amber-400 mb-2" />
            <p className="text-2xl font-bold">{value}</p>
            <p className="text-zinc-400 text-sm">{label}</p>
          </div>
        ))}
      </div>

      {/* Run scrapers */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mb-8">
        <h2 className="font-semibold mb-4">Scraper Status</h2>
        <div className="space-y-2 mb-4">
          {lastRunByCinema.map(({ cinema, log }) => (
            <div key={cinema.id} className="flex items-center justify-between text-sm">
              <span className="text-zinc-300">{cinema.name_en}</span>
              <div className="flex items-center gap-2 text-zinc-400">
                {log ? (
                  <>
                    <StatusIcon status={log.status} />
                    <span>{new Date(log.ran_at).toLocaleString()}</span>
                    <span className="text-zinc-500">({log.showtimes_found} showtimes)</span>
                  </>
                ) : (
                  <span className="text-zinc-600">Never run</span>
                )}
              </div>
            </div>
          ))}
        </div>
        <button
          onClick={runScrapers}
          disabled={running}
          className="flex items-center gap-2 bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-black font-semibold px-4 py-2 rounded-lg transition-colors text-sm"
        >
          <Play size={14} />
          {running ? 'Running...' : 'Run Scrapers Now'}
        </button>
        {runResult && (
          <p className={`mt-3 text-sm ${runResult.startsWith('✓') ? 'text-green-400' : 'text-red-400'}`}>
            {runResult}
          </p>
        )}
        <p className="mt-2 text-xs text-zinc-600">
          Note: "Run now" only works when self-hosted. On Vercel free tier, run the scraper manually via command line.
        </p>
      </div>

      {/* Recent logs */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-zinc-800">
          <h2 className="font-semibold">Recent Scraper Logs</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                <th className="text-left p-3">Cinema</th>
                <th className="text-left p-3">Status</th>
                <th className="text-left p-3">Showtimes</th>
                <th className="text-left p-3">Duration</th>
                <th className="text-left p-3">Time</th>
              </tr>
            </thead>
            <tbody>
              {logs.map(log => (
                <tr key={log.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                  <td className="p-3 text-zinc-300">{log.cinemas?.name_en ?? '—'}</td>
                  <td className="p-3">
                    <span className={`flex items-center gap-1.5 ${log.status === 'success' ? 'text-green-400' : log.status === 'failed' ? 'text-red-400' : 'text-yellow-400'}`}>
                      <StatusIcon status={log.status} />
                      {log.status}
                    </span>
                  </td>
                  <td className="p-3 text-zinc-400">{log.showtimes_found}</td>
                  <td className="p-3 text-zinc-400">{log.duration_ms ? `${(log.duration_ms / 1000).toFixed(1)}s` : '—'}</td>
                  <td className="p-3 text-zinc-500">{new Date(log.ran_at).toLocaleString()}</td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr><td colSpan={5} className="p-6 text-center text-zinc-600">No logs yet — run the scraper first</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
