import { getLocale, getTranslations } from 'next-intl/server'
import { notFound } from 'next/navigation'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/server'
import { toJordanDate, formatTime12h } from '@/lib/utils'
import Header from '@/components/Header'
import ChatBot from '@/components/ChatBot'
import MovieCard from '@/components/MovieCard'
import { MapPin, ArrowLeft, ExternalLink } from 'lucide-react'

export default async function CinemaPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const locale = await getLocale()
  const t = await getTranslations()
  const supabase = await createClient()

  const { data: cinema } = await supabase
    .from('cinemas')
    .select('*')
    .eq('slug', slug)
    .single()

  if (!cinema) notFound()

  const today = toJordanDate()
  const { data: showtimes } = await supabase
    .from('showtimes')
    .select('*, movies(*)')
    .eq('cinema_id', cinema.id)
    .eq('show_date', today)
    .order('show_time')

  const isArabic = locale === 'ar'
  const name = isArabic ? cinema.name_ar : cinema.name_en
  const address = isArabic ? cinema.address_ar : cinema.address_en

  // Group by movie
  const movieMap = new Map<string, { movie: any; times: typeof showtimes }>()
  for (const st of showtimes ?? []) {
    if (!st?.movies) continue
    const mid = st.movie_id
    if (!movieMap.has(mid)) movieMap.set(mid, { movie: st.movies, times: [] })
    movieMap.get(mid)!.times!.push(st)
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <Header locale={locale} />
      <main className="max-w-5xl mx-auto px-4 py-8">
        <Link href="/" className="inline-flex items-center gap-1.5 text-zinc-400 hover:text-white text-sm mb-6 transition-colors">
          <ArrowLeft size={16} className={isArabic ? 'rotate-180' : ''} />
          {t('common.backToHome')}
        </Link>

        {/* Cinema header */}
        <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-6 mb-8">
          <h1 className="text-2xl font-bold text-white mb-2">{name}</h1>
          {address && (
            <p className="flex items-center gap-2 text-zinc-400 text-sm mb-3">
              <MapPin size={14} className="text-amber-400 shrink-0" />
              {address}
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            {cinema.google_maps_url && (
              <a
                href={cinema.google_maps_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded-lg transition-colors"
              >
                <MapPin size={14} />
                {t('cinema.getDirections')}
              </a>
            )}
            {cinema.website_url && (
              <a
                href={cinema.website_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-3 py-1.5 rounded-lg transition-colors"
              >
                <ExternalLink size={14} />
                Website
              </a>
            )}
          </div>
        </div>

        {/* Now showing */}
        <h2 className="text-xl font-bold mb-4">{t('cinema.nowShowing')}</h2>
        {movieMap.size === 0 ? (
          <p className="text-zinc-500 text-center py-12">{t('cinema.noMovies')}</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {Array.from(movieMap.values()).map(({ movie, times }) => (
              <MovieCard
                key={movie.id}
                movie={movie}
                showtimes={times ?? []}
                locale={locale}
              />
            ))}
          </div>
        )}
      </main>
      <ChatBot locale={locale} />
    </div>
  )
}
