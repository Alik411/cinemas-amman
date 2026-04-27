import Link from 'next/link'
import Image from 'next/image'
import { Clock } from 'lucide-react'
import type { Movie, Showtime } from '@/types/database'
import PosterPlaceholder from './PosterPlaceholder'
import { formatTime12h } from '@/lib/utils'

interface MovieCardProps {
  movie: Movie
  showtimes?: Showtime[]
  locale: string
}

export default function MovieCard({ movie, showtimes = [], locale }: MovieCardProps) {
  const title = locale === 'ar' && movie.title_ar ? movie.title_ar : movie.title_en
  const uniqueTimes = Array.from(new Set(showtimes.map(s => s.show_time))).slice(0, 4)

  return (
    <Link href={`/movies/${movie.slug}`} className="group block">
      <div className="bg-zinc-900 rounded-xl overflow-hidden border border-zinc-800 hover:border-amber-500/50 transition-all duration-200 hover:scale-[1.02]">
        <div className="relative aspect-[2/3] w-full">
          {movie.poster_url ? (
            <Image
              src={movie.poster_url}
              alt={title}
              fill
              className="object-cover"
              sizes="(max-width: 768px) 45vw, 200px"
            />
          ) : (
            <PosterPlaceholder title={title} className="absolute inset-0" />
          )}
          {movie.age_rating && (
            <span className="absolute top-2 right-2 rtl:right-auto rtl:left-2 bg-black/70 text-xs text-zinc-300 px-1.5 py-0.5 rounded">
              {movie.age_rating}
            </span>
          )}
        </div>
        <div className="p-3">
          <h3 className="font-semibold text-white text-sm leading-tight line-clamp-2 mb-1">{title}</h3>
          {movie.genre_tags && movie.genre_tags.length > 0 && (
            <p className="text-xs text-zinc-400 mb-2 truncate">
              {movie.genre_tags.slice(0, 2).join(' · ')}
            </p>
          )}
          {uniqueTimes.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {uniqueTimes.map(time => (
                <span key={time} className="text-xs bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded font-medium">
                  {formatTime12h(time)}
                </span>
              ))}
              {showtimes.length > 4 && (
                <span className="text-xs text-zinc-500 flex items-center gap-0.5">
                  <Clock size={10} /> +{showtimes.length - 4}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </Link>
  )
}
