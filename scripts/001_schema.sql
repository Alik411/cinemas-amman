-- ─────────────────────────────────────────────────────────────────────────────
-- CineAmman — Database Schema + Row Level Security
-- Run this entire file in: Supabase → SQL Editor → New query → Paste → Run
-- ─────────────────────────────────────────────────────────────────────────────


-- ── Cinemas ───────────────────────────────────────────────────────────────────
CREATE TABLE cinemas (
  id               UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  name_en          TEXT        NOT NULL,
  name_ar          TEXT        NOT NULL,
  slug             TEXT        UNIQUE NOT NULL,
  mall_name_en     TEXT,
  mall_name_ar     TEXT,
  address_en       TEXT,
  address_ar       TEXT,
  google_maps_url  TEXT,
  logo_url         TEXT,
  website_url      TEXT,
  scraper_url      TEXT        NOT NULL,
  active           BOOLEAN     DEFAULT true,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE cinemas ENABLE ROW LEVEL SECURITY;
-- Anyone can read cinemas; only service_role (server) can write
CREATE POLICY "Public can read cinemas"
  ON cinemas FOR SELECT USING (true);


-- ── Movies ────────────────────────────────────────────────────────────────────
CREATE TABLE movies (
  id                  UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  title_en            TEXT        NOT NULL,
  title_ar            TEXT,
  slug                TEXT        UNIQUE NOT NULL,
  synopsis_en         TEXT,
  synopsis_ar         TEXT,
  genre_tags          TEXT[],
  age_rating          TEXT,
  duration_mins       INTEGER,
  poster_url          TEXT,
  trailer_youtube_id  TEXT,
  tmdb_id             INTEGER,
  enriched_at         TIMESTAMPTZ,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE movies ENABLE ROW LEVEL SECURITY;
-- Anyone can read movies; only service_role (server) can write
CREATE POLICY "Public can read movies"
  ON movies FOR SELECT USING (true);


-- ── Showtimes ─────────────────────────────────────────────────────────────────
CREATE TABLE showtimes (
  id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  movie_id     UUID        REFERENCES movies(id)  ON DELETE CASCADE,
  cinema_id    UUID        REFERENCES cinemas(id) ON DELETE CASCADE,
  show_date    DATE        NOT NULL,
  show_time    TIME        NOT NULL,
  screen_type  TEXT        DEFAULT '2D',
  language     TEXT        DEFAULT 'English',
  booking_url  TEXT,
  scraped_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (movie_id, cinema_id, show_date, show_time, screen_type, language)
);

ALTER TABLE showtimes ENABLE ROW LEVEL SECURITY;
-- Anyone can read showtimes; only service_role (server) can write
CREATE POLICY "Public can read showtimes"
  ON showtimes FOR SELECT USING (true);


-- ── Scraper logs ──────────────────────────────────────────────────────────────
CREATE TABLE scraper_logs (
  id                UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  cinema_id         UUID        REFERENCES cinemas(id),
  status            TEXT        NOT NULL,
  showtimes_found   INTEGER     DEFAULT 0,
  movies_found      INTEGER     DEFAULT 0,
  error_message     TEXT,
  duration_ms       INTEGER,
  ran_at            TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE scraper_logs ENABLE ROW LEVEL SECURITY;
-- No public access — only service_role can read/write scraper logs
-- (The admin dashboard uses a server-side API route with service_role key)


-- ── Newsletter subscribers ────────────────────────────────────────────────────
CREATE TABLE subscribers (
  id              UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  email           TEXT        UNIQUE NOT NULL,
  language_pref   TEXT        DEFAULT 'en',
  active          BOOLEAN     DEFAULT true,
  subscribed_at   TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE subscribers ENABLE ROW LEVEL SECURITY;
-- Anyone can subscribe (insert their own email); nobody can read others' emails
CREATE POLICY "Anyone can subscribe"
  ON subscribers FOR INSERT WITH CHECK (true);


-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX idx_showtimes_date       ON showtimes (show_date);
CREATE INDEX idx_showtimes_movie      ON showtimes (movie_id);
CREATE INDEX idx_showtimes_cinema     ON showtimes (cinema_id);
CREATE INDEX idx_scraper_logs_cinema  ON scraper_logs (cinema_id);
CREATE INDEX idx_scraper_logs_ran_at  ON scraper_logs (ran_at DESC);
