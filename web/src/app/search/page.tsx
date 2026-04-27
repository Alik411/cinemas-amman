'use client'

import { useState } from 'react'
import { useTranslations } from 'next-intl'
import Link from 'next/link'
import { Search } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import MovieCard from '@/components/MovieCard'
import type { Movie, Cinema } from '@/types/database'

export default function SearchPage() {
  const t = useTranslations('search')
  const [query, setQuery] = useState('')
  const [movies, setMovies] = useState<Movie[]>([])
  const [cinemas, setCinemas] = useState<Cinema[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  async function doSearch(q: string) {
    if (!q.trim()) {
      setMovies([])
      setCinemas([])
      setSearched(false)
      return
    }
    setLoading(true)
    setSearched(true)
    const supabase = createClient()

    const [moviesRes, cinemasRes] = await Promise.all([
      supabase.from('movies').select('*').or(`title_en.ilike.%${q}%,title_ar.ilike.%${q}%`).limit(12),
      supabase.from('cinemas').select('*').or(`name_en.ilike.%${q}%,name_ar.ilike.%${q}%`).eq('active', true).limit(6),
    ])

    setMovies(moviesRes.data ?? [])
    setCinemas(cinemasRes.data ?? [])
    setLoading(false)
  }

  let debounceTimer: ReturnType<typeof setTimeout>
  function handleInput(val: string) {
    setQuery(val)
    clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => doSearch(val), 350)
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="relative mb-8">
          <Search size={18} className="absolute left-4 rtl:left-auto rtl:right-4 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            autoFocus
            type="text"
            value={query}
            onChange={e => handleInput(e.target.value)}
            placeholder={t('placeholder')}
            className="w-full bg-zinc-900 border border-zinc-700 text-white placeholder:text-zinc-500 rounded-xl pl-11 rtl:pl-4 rtl:pr-11 pr-4 py-3.5 text-base focus:outline-none focus:border-amber-500"
          />
        </div>

        {loading && (
          <p className="text-zinc-400 text-center py-8">{t('noResults')}</p>
        )}

        {searched && !loading && movies.length === 0 && cinemas.length === 0 && (
          <div className="text-center py-16 text-zinc-500">
            <p className="text-lg">{t('noResults')}</p>
            <p className="text-sm mt-2">{t('noResultsHint')}</p>
          </div>
        )}

        {movies.length > 0 && (
          <section className="mb-8">
            <h2 className="text-lg font-semibold mb-4 text-zinc-300">{t('movies')}</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {movies.map(m => <MovieCard key={m.id} movie={m} locale="en" />)}
            </div>
          </section>
        )}

        {cinemas.length > 0 && (
          <section>
            <h2 className="text-lg font-semibold mb-4 text-zinc-300">{t('cinemas')}</h2>
            <div className="grid sm:grid-cols-2 gap-3">
              {cinemas.map(c => (
                <Link key={c.id} href={`/cinemas/${c.slug}`}
                  className="bg-zinc-900 border border-zinc-800 hover:border-amber-500/50 rounded-xl p-4 transition-colors">
                  <p className="font-semibold text-white">{c.name_en}</p>
                  {c.name_ar && <p className="text-zinc-400 text-sm mt-0.5">{c.name_ar}</p>}
                  {c.address_en && <p className="text-zinc-500 text-xs mt-2">{c.address_en}</p>}
                </Link>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
