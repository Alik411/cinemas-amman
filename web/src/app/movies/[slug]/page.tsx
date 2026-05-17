import { getLocale, getTranslations } from 'next-intl/server'
import { notFound } from 'next/navigation'
import Image from 'next/image'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/server'
import { formatTime12h, formatDate, toJordanDate, getTomorrowJordan } from '@/lib/utils'
import Header from '@/components/Header'
import ChatBot from '@/components/ChatBot'
import PosterPlaceholder from '@/components/PosterPlaceholder'
import MovieCard from '@/components/MovieCard'
import { Clock, Star, Calendar, ArrowLeft } from 'lucide-react'
import type { ShowtimeWithRelations, Movie } from '@/types/database'

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const { createClient } = await import('@/lib/supabase/server')
  const supabase = await createClient()
  const { data: movie } = await supabase
    .from('movies')
    .select('title_en, title_ar, synopsis_en, synopsis_ar, genre_tags, poster_url')
    .eq('slug', slug)
    .single()
  if (!movie) return {}

  const titleEn = `${movie.title_en} Showtimes in Amman | CineAmman`
  const titleAr = movie.title_ar
    ? `أوقات عرض ${movie.title_ar} في عمّان | سينما عمّان`
    : titleEn
  const descEn = movie.synopsis_en
    ? `${movie.synopsis_en.slice(0, 140)}... Book tickets for ${movie.title_en} at Amman cinemas.`
    : `Showtimes and tickets for ${movie.title_en} at Grand Cinemas, Prime Cinemas and Taj Cinemas in Amman.`
  const descAr = movie.synopsis_ar
    ? `${movie.synopsis_ar.slice(0, 140)}... احجز تذاكر ${movie.title_ar ?? movie.title_en} في سينمات عمّان.`
    : descEn

  return {
    title: titleEn,
    description: descEn,
    keywords: [
      movie.title_en, movie.title_ar ?? '',
      `${movie.title_en} amman`, `${movie.title_en} showtimes`,
      `${movie.title_ar ?? ''} عمان`, 'سينما عمان',
    ].filter(Boolean),
    alternates: {
      canonical: `https://www.cineamman.com/movies/${slug}`,
    },
    openGraph: {
      title: titleAr,
      description: descAr,
      images: movie.poster_url ? [{ url: movie.poster_url, width: 500, height: 750 }] : [],
      type: 'video.movie',
    },
  }
}

export default async function MoviePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const locale = await getLocale()
  const t = await getTranslations()
  const supabase = await createClient()

  const { data: movie } = await supabase
    .from('movies')
    .select('*')
    .eq('slug', slug)
    .single()

  if (!movie) notFound()

  const today = toJordanDate()
  const tomorrow = getTomorrowJordan()

  const { data: showtimes } = await supabase
    .from('showtimes')
    .select('*, cinemas(*)')
    .eq('movie_id', movie.id)
    .gte('show_date', today)
    .lte('show_date', tomorrow)
    .order('show_date')
    .order('show_time')

  // Related movies by genre
  const { data: related } = await supabase
    .from('movies')
    .select('*')
    .neq('id', movie.id)
    .overlaps('genre_tags', movie.genre_tags ?? [])
    .limit(3)

  const title = locale === 'ar' && movie.title_ar ? movie.title_ar : movie.title_en
  const synopsis = locale === 'ar' && movie.synopsis_ar ? movie.synopsis_ar : movie.synopsis_en
  const isArabic = locale === 'ar'

  // Group showtimes by date then cinema
  const byDate = (showtimes ?? []).reduce<Record<string, typeof showtimes>>((acc, st) => {
    if (!st) return acc
    const d = st.show_date
    if (!acc[d]) acc[d] = []
    acc[d]!.push(st)
    return acc
  }, {})

  // JSON-LD: Movie + ScreeningEvent for each showtime
  const jsonLd = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Movie',
        '@id': `https://www.cineamman.com/movies/${slug}#movie`,
        name: movie.title_en,
        alternateName: movie.title_ar ?? undefined,
        description: movie.synopsis_en ?? undefined,
        image: movie.poster_url ?? undefined,
        genre: movie.genre_tags ?? [],
        duration: movie.duration_mins ? `PT${movie.duration_mins}M` : undefined,
        contentRating: movie.age_rating ?? undefined,
      },
      ...(showtimes ?? []).map(st => ({
        '@type': 'ScreeningEvent',
        name: `${title} — ${(st as any).cinemas?.name_en ?? ''}`,
        startDate: `${st.show_date}T${st.show_time}`,
        url: st.booking_url ?? `https://www.cineamman.com/movies/${slug}`,
        location: {
          '@type': 'MovieTheater',
          name: (st as any).cinemas?.name_en ?? '',
          address: { '@type': 'PostalAddress', addressLocality: 'Amman', addressCountry: 'JO' },
        },
        workPresented: { '@id': `https://www.cineamman.com/movies/${slug}#movie` },
        offers: st.booking_url
          ? { '@type': 'Offer', url: st.booking_url, availability: 'https://schema.org/InStock', priceCurrency: 'JOD' }
          : undefined,
      })),
    ],
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <Header locale={locale} />
      <main className="max-w-6xl mx-auto px-4 py-8">
        <Link href="/" className="inline-flex items-center gap-1.5 text-zinc-400 hover:text-white text-sm mb-6 transition-colors">
          <ArrowLeft size={16} className={isArabic ? 'rotate-180' : ''} />
          {t('common.backToHome')}
        </Link>

        {/* Movie header */}
        <div className="flex flex-col md:flex-row gap-8 mb-10">
          <div className="w-full md:w-56 shrink-0">
            <div className="relative aspect-[2/3] rounded-xl overflow-hidden">
              {movie.poster_url ? (
                <Image src={movie.poster_url} alt={title} fill className="object-cover" sizes="224px" />
              ) : (
                <PosterPlaceholder title={title} className="absolute inset-0" />
              )}
            </div>
          </div>

          <div className="flex-1">
            <h1 className="text-2xl sm:text-3xl font-bold text-white mb-1">{title}</h1>
            {movie.title_ar && movie.title_en && (
              <p className="text-zinc-400 text-lg mb-4">{isArabic ? movie.title_en : movie.title_ar}</p>
            )}

            <div className="flex flex-wrap gap-4 text-sm text-zinc-300 mb-4">
              {movie.age_rating && (
                <span className="flex items-center gap-1">
                  <Star size={14} className="text-amber-400" />
                  {movie.age_rating}
                </span>
              )}
              {movie.duration_mins && (
                <span className="flex items-center gap-1">
                  <Clock size={14} className="text-amber-400" />
                  {movie.duration_mins} {t('movie.minutes')}
                </span>
              )}
            </div>

            {movie.genre_tags && movie.genre_tags.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-4">
                {movie.genre_tags.map((g: string) => (
                  <span key={g} className="text-xs bg-zinc-800 text-zinc-300 px-2.5 py-1 rounded-full border border-zinc-700">
                    {g}
                  </span>
                ))}
              </div>
            )}

            {synopsis && (
              <div>
                <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide mb-2">{t('movie.synopsis')}</h2>
                <p className="text-zinc-300 leading-relaxed">{synopsis}</p>
              </div>
            )}

            {movie.trailer_youtube_id && (
              <a
                href={`https://www.youtube.com/watch?v=${movie.trailer_youtube_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-4 inline-flex items-center gap-2 bg-red-600 hover:bg-red-500 text-white text-sm px-4 py-2 rounded-lg transition-colors"
              >
                ▶ {t('movie.trailer')}
              </a>
            )}
          </div>
        </div>

        {/* Showtimes */}
        <section className="mb-12">
          <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
            <Calendar size={20} className="text-amber-400" />
            {t('movie.showtimes')}
          </h2>

          {Object.keys(byDate).length === 0 ? (
            <p className="text-zinc-500 text-center py-8">{t('movie.noShowtimes')}</p>
          ) : (
            <div className="space-y-4">
              {Object.entries(byDate).map(([date, times]) => {
                const label = date === today ? t('common.today') : date === tomorrow ? t('common.tomorrow') : formatDate(date, locale)
                const byCinema = (times ?? []).reduce<Record<string, typeof times>>((acc, st) => {
                  if (!st) return acc
                  const cId = st.cinema_id
                  if (!acc[cId]) acc[cId] = []
                  acc[cId]!.push(st)
                  return acc
                }, {})

                return (
                  <div key={date} className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
                    <h3 className="font-semibold text-amber-400 mb-3">{label}</h3>
                    {Object.entries(byCinema).map(([cId, cTimes]) => {
                      const cinema = (cTimes?.[0] as any)?.cinemas
                      const cinemaName = cinema ? (isArabic ? cinema.name_ar : cinema.name_en) : cId
                      return (
                        <div key={cId} className="flex flex-wrap items-center gap-3 mb-2 last:mb-0">
                          <span className="text-sm text-zinc-400 w-44 shrink-0 truncate">{cinemaName}</span>
                          <div className="flex flex-wrap gap-2">
                            {(cTimes ?? []).map(st => (
                              <a
                                key={st!.id}
                                href={st!.booking_url ?? '#'}
                                target={st!.booking_url ? '_blank' : undefined}
                                rel="noopener noreferrer"
                                className="text-sm bg-amber-500/20 hover:bg-amber-500/40 text-amber-400 px-3 py-1.5 rounded-lg font-medium transition-colors"
                              >
                                {formatTime12h(st!.show_time)}
                                {st!.screen_type !== '2D' && (
                                  <span className="ms-1.5 text-xs text-zinc-400">{st!.screen_type}</span>
                                )}
                              </a>
                            ))}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          )}
        </section>

        {/* Related movies */}
        {related && related.length > 0 && (
          <section>
            <h2 className="text-xl font-bold mb-4">{t('movie.youMightAlsoLike')}</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              {related.map(m => (
                <MovieCard key={m.id} movie={m} locale={locale} />
              ))}
            </div>
          </section>
        )}
      </main>
      <ChatBot locale={locale} />
    </div>
  )
}
