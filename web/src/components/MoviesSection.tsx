'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Film } from 'lucide-react'
import MovieCard from '@/components/MovieCard'
import { formatTime12h } from '@/lib/utils'
import type { Movie, Showtime, Cinema } from '@/types/database'

interface MovieWithShowtimes {
  movie: Movie
  showtimes: Showtime[]
}

interface MoviesSectionProps {
  moviesWithShowtimes: MovieWithShowtimes[]
  cinemas: Cinema[]
  locale: string
}

export default function MoviesSection({ moviesWithShowtimes, cinemas, locale }: MoviesSectionProps) {
  const t = useTranslations('home')
  const [cinemaFilter, setCinemaFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  const filtered = moviesWithShowtimes
    .map(({ movie, showtimes }) => {
      let times = showtimes
      if (cinemaFilter) times = times.filter(s => s.cinema_id === cinemaFilter)
      if (typeFilter) times = times.filter(s => s.screen_type === typeFilter)
      return { movie, showtimes: times }
    })
    .filter(({ showtimes }) => showtimes.length > 0)

  return (
    <>
      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={cinemaFilter}
          onChange={e => setCinemaFilter(e.target.value)}
          className="bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500"
        >
          <option value="">{t('filterByCinema')}</option>
          {cinemas.map(c => (
            <option key={c.id} value={c.id}>
              {locale === 'ar' ? c.name_ar : c.name_en}
            </option>
          ))}
        </select>

        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500"
        >
          <option value="">{t('filterByType')}</option>
          <option value="2D">2D</option>
          <option value="3D">3D</option>
          <option value="IMAX">IMAX</option>
          <option value="4DX">4DX</option>
        </select>

        {(cinemaFilter || typeFilter) && (
          <button
            onClick={() => { setCinemaFilter(''); setTypeFilter('') }}
            className="text-xs text-zinc-400 hover:text-white px-3 py-2 rounded-lg border border-zinc-700 hover:border-zinc-500 transition-colors"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Now Showing */}
      <section className="mt-8">
        <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
          <Film size={20} className="text-amber-400" />
          {t('nowShowing')}
        </h2>

        {filtered.length === 0 ? (
          <div className="text-center py-16 text-zinc-500">
            <Film size={48} className="mx-auto mb-4 opacity-30" />
            <p className="text-lg">{t('noShowtimes')}</p>
            <p className="text-sm mt-2">{t('noShowtimesHint')}</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4">
            {filtered.map(({ movie, showtimes: times }) => (
              <MovieCard key={movie.id} movie={movie} showtimes={times} locale={locale} />
            ))}
          </div>
        )}
      </section>

      {/* Full showtime grid */}
      {filtered.length > 0 && (
        <section className="mt-12">
          <h2 className="text-xl font-bold mb-6">{t('todaysShowtimes')}</h2>
          <div className="space-y-4">
            {filtered.map(({ movie, showtimes: times }) => {
              const title = locale === 'ar' && movie.title_ar ? movie.title_ar : movie.title_en
              const byCinema = cinemas
                .map(cinema => ({
                  cinema,
                  times: times.filter(s => s.cinema_id === cinema.id),
                }))
                .filter(({ times: t }) => t.length > 0)

              if (byCinema.length === 0) return null

              return (
                <div key={movie.id} className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
                  <h3 className="font-semibold text-white mb-3">{title}</h3>
                  <div className="space-y-2">
                    {byCinema.map(({ cinema, times: cTimes }) => {
                      const cinemaName = locale === 'ar' ? cinema.name_ar : cinema.name_en
                      return (
                        <div key={cinema.id} className="flex flex-wrap items-center gap-2">
                          <span className="text-xs text-zinc-400 w-40 shrink-0 truncate">{cinemaName}</span>
                          <div className="flex flex-wrap gap-1.5">
                            {cTimes.map(st => (
                              <a
                                key={st.id}
                                href={st.booking_url ?? '#'}
                                target={st.booking_url ? '_blank' : undefined}
                                rel="noopener noreferrer"
                                className="text-xs bg-amber-500/20 hover:bg-amber-500/40 text-amber-400 px-2 py-1 rounded-md font-medium transition-colors"
                              >
                                {formatTime12h(st.show_time)}
                                {st.screen_type !== '2D' && (
                                  <span className="ms-1 text-zinc-400">{st.screen_type}</span>
                                )}
                              </a>
                            ))}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}
    </>
  )
}
