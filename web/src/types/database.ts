export interface Cinema {
  id: string
  name_en: string
  name_ar: string
  slug: string
  mall_name_en: string | null
  mall_name_ar: string | null
  address_en: string | null
  address_ar: string | null
  google_maps_url: string | null
  logo_url: string | null
  website_url: string | null
  scraper_url: string
  active: boolean
  created_at: string
}

export interface Movie {
  id: string
  title_en: string
  title_ar: string | null
  slug: string
  synopsis_en: string | null
  synopsis_ar: string | null
  genre_tags: string[] | null
  age_rating: string | null
  duration_mins: number | null
  poster_url: string | null
  trailer_youtube_id: string | null
  tmdb_id: number | null
  enriched_at: string | null
  created_at: string
}

export interface Showtime {
  id: string
  movie_id: string
  cinema_id: string
  show_date: string
  show_time: string
  screen_type: string
  language: string
  booking_url: string | null
  scraped_at: string
}

export interface ShowtimeWithRelations extends Showtime {
  movies: Movie
  cinemas: Cinema
}

export interface ScraperLog {
  id: string
  cinema_id: string | null
  status: 'success' | 'failed' | 'partial'
  showtimes_found: number
  movies_found: number
  error_message: string | null
  duration_ms: number | null
  ran_at: string
  cinemas?: Pick<Cinema, 'name_en' | 'name_ar' | 'slug'>
}

export interface Subscriber {
  id: string
  email: string
  language_pref: string
  active: boolean
  subscribed_at: string
}
