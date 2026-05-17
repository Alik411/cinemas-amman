import { getTranslations, getLocale } from 'next-intl/server'
import { createClient } from '@/lib/supabase/server'
import { toJordanDate } from '@/lib/utils'
import Header from '@/components/Header'
import ChatBot from '@/components/ChatBot'
import MoviesSection from '@/components/MoviesSection'
import type { Movie, Showtime, Cinema } from '@/types/database'

// JSON-LD for Google: WebSite + SearchAction
function HomeJsonLd({ locale }: { locale: string }) {
  const isAr = locale === 'ar'
  const data = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'WebSite',
        '@id': 'https://www.cineamman.com/#website',
        url: 'https://www.cineamman.com',
        name: isAr ? 'سينما عمّان' : 'CineAmman',
        description: isAr
          ? 'جميع أوقات عروض سينمات عمّان في مكان واحد'
          : 'All Amman cinema showtimes in one place',
        inLanguage: ['ar', 'en'],
        potentialAction: {
          '@type': 'SearchAction',
          target: 'https://www.cineamman.com/search?q={search_term_string}',
          'query-input': 'required name=search_term_string',
        },
      },
      {
        '@type': 'Organization',
        '@id': 'https://www.cineamman.com/#org',
        name: 'CineAmman',
        url: 'https://www.cineamman.com',
        logo: 'https://www.cineamman.com/icon.png',
        areaServed: { '@type': 'City', name: 'Amman', containedInPlace: { '@type': 'Country', name: 'Jordan' } },
      },
    ],
  }
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  )
}

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>
}) {
  const { date: dateParam } = await searchParams
  const locale = await getLocale()
  const t = await getTranslations()
  const supabase = await createClient()
  const today = toJordanDate()

  // Validate the date param — must be a real YYYY-MM-DD in the next 7 days
  const maxDate = (() => {
    const d = new Date(today)
    d.setDate(d.getDate() + 6)
    return d.toISOString().slice(0, 10)
  })()
  const selectedDate =
    dateParam && /^\d{4}-\d{2}-\d{2}$/.test(dateParam) &&
    dateParam >= today && dateParam <= maxDate
      ? dateParam
      : today

  const [moviesRes, showtimesRes, cinemasRes, allDatesRes] = await Promise.all([
    supabase.from('movies').select('*').order('created_at', { ascending: false }),
    supabase.from('showtimes').select('*').eq('show_date', selectedDate),
    supabase.from('cinemas').select('*').eq('active', true),
    // Get all distinct dates with showtimes in the next 7 days for the date strip
    supabase
      .from('showtimes')
      .select('show_date')
      .gte('show_date', today)
      .lte('show_date', maxDate),
  ])

  const movies: Movie[] = moviesRes.data ?? []
  const showtimes: Showtime[] = showtimesRes.data ?? []
  const cinemas: Cinema[] = cinemasRes.data ?? []

  // Deduplicate dates
  const availableDates = [...new Set((allDatesRes.data ?? []).map(r => r.show_date))].sort()

  const moviesWithShowtimes = movies
    .filter(m => showtimes.some(s => s.movie_id === m.id))
    .map(m => ({
      movie: m,
      showtimes: showtimes.filter(s => s.movie_id === m.id),
    }))

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <HomeJsonLd locale={locale} />
      <Header locale={locale} />

      {/* Hero — compact on mobile so movies are visible immediately */}
      <section className="relative overflow-hidden bg-gradient-to-b from-zinc-900 to-zinc-950 py-6 sm:py-14 px-4 text-center">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-amber-900/20 via-transparent to-transparent" />
        <div className="relative max-w-2xl mx-auto">
          <h1 className="text-3xl sm:text-5xl font-bold">
            <span className="text-amber-400">{locale === 'ar' ? 'سينما عمّان' : 'CineAmman'}</span>
          </h1>
          <p className="text-zinc-400 text-sm sm:text-base mt-2 hidden sm:block">{t('hero.subtitle')}</p>
        </div>
      </section>

      <main className="max-w-7xl mx-auto px-4 py-6">
        <MoviesSection
          moviesWithShowtimes={moviesWithShowtimes}
          cinemas={cinemas}
          locale={locale}
          selectedDate={selectedDate}
          availableDates={availableDates}
          today={today}
        />
      </main>

      <footer className="text-center text-xs text-zinc-600 py-6 px-4">
        {locale === 'ar'
          ? 'البيانات مصدرها مواقع دور السينما؛ تحقق قبل الحجز.'
          : 'Data sourced from cinema websites; verify before booking.'}
      </footer>

      <ChatBot locale={locale} />
    </div>
  )
}
