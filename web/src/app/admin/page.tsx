import { getTranslations } from 'next-intl/server'
import { createServiceClient } from '@/lib/supabase/server'
import AdminClient from './AdminClient'
import type { ScraperLog, Cinema } from '@/types/database'

export default async function AdminPage() {
  const t = await getTranslations('admin')
  const supabase = createServiceClient()

  const [logsRes, cinemasRes, moviesRes, showtimesRes] = await Promise.all([
    supabase
      .from('scraper_logs')
      .select('*, cinemas(name_en, name_ar, slug)')
      .order('ran_at', { ascending: false })
      .limit(50),
    supabase.from('cinemas').select('*'),
    supabase.from('movies').select('id', { count: 'exact', head: true }),
    supabase.from('showtimes').select('id', { count: 'exact', head: true }),
  ])

  return (
    <AdminClient
      logs={logsRes.data ?? []}
      cinemas={cinemasRes.data ?? []}
      movieCount={moviesRes.count ?? 0}
      showtimeCount={showtimesRes.count ?? 0}
    />
  )
}
