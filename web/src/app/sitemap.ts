import { createClient } from '@/lib/supabase/server'
import type { MetadataRoute } from 'next'

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const supabase = await createClient()
  const base = 'https://www.cineamman.com'

  const [moviesRes, cinemasRes] = await Promise.all([
    supabase.from('movies').select('slug, updated_at'),
    supabase.from('cinemas').select('slug').eq('active', true),
  ])

  const movieUrls = (moviesRes.data ?? []).map(m => ({
    url: `${base}/movies/${m.slug}`,
    lastModified: m.updated_at ? new Date(m.updated_at) : new Date(),
    changeFrequency: 'daily' as const,
    priority: 0.8,
  }))

  const cinemaUrls = (cinemasRes.data ?? []).map(c => ({
    url: `${base}/cinemas/${c.slug}`,
    lastModified: new Date(),
    changeFrequency: 'daily' as const,
    priority: 0.7,
  }))

  return [
    {
      url: base,
      lastModified: new Date(),
      changeFrequency: 'hourly',
      priority: 1,
    },
    ...movieUrls,
    ...cinemaUrls,
  ]
}
