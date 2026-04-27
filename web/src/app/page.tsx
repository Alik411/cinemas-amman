import { getTranslations, getLocale } from 'next-intl/server'
import { createClient } from '@/lib/supabase/server'
import { toJordanDate } from '@/lib/utils'
import Header from '@/components/Header'
import ChatBot from '@/components/ChatBot'
import MoviesSection from '@/components/MoviesSection'
import type { Movie, Showtime, Cinema } from '@/types/database'

export default async function HomePage() {
  const locale = await getLocale()
  const t = await getTranslations()
  const supabase = await createClient()
  const today = toJordanDate()

  const [moviesRes, showtimesRes, cinemasRes] = await Promise.all([
    supabase.from('movies').select('*').order('created_at', { ascending: false }),
    supabase.from('showtimes').select('*').eq('show_date', today),
    supabase.from('cinemas').select('*').eq('active', true),
  ])

  const movies: Movie[] = moviesRes.data ?? []
  const showtimes: Showtime[] = showtimesRes.data ?? []
  const cinemas: Cinema[] = cinemasRes.data ?? []

  const moviesWithShowtimes = movies
    .filter(m => showtimes.some(s => s.movie_id === m.id))
    .map(m => ({
      movie: m,
      showtimes: showtimes.filter(s => s.movie_id === m.id),
    }))

  const isArabic = locale === 'ar'

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <Header locale={locale} />

      {/* Hero */}
      <section className="relative overflow-hidden bg-gradient-to-b from-zinc-900 to-zinc-950 py-16 px-4 text-center">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-amber-900/20 via-transparent to-transparent" />
        <div className="relative max-w-2xl mx-auto">
          <h1 className="text-4xl sm:text-5xl font-bold mb-3">
            <span className="text-amber-400">{isArabic ? 'سينما عمّان' : 'CineAmman'}</span>
          </h1>
          <p className="text-zinc-300 text-lg mb-2">
            {isArabic ? 'CineAmman' : 'سينما عمّان'}
          </p>
          <p className="text-zinc-400 text-base">{t('hero.subtitle')}</p>
        </div>
      </section>

      <main className="max-w-7xl mx-auto px-4 py-8">
        <MoviesSection
          moviesWithShowtimes={moviesWithShowtimes}
          cinemas={cinemas}
          locale={locale}
        />
      </main>

      <footer className="text-center text-xs text-zinc-600 py-6 px-4">
        Data sourced from cinema websites; verify before booking.
      </footer>

      <ChatBot locale={locale} />
    </div>
  )
}
