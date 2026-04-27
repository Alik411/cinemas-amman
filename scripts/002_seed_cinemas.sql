-- ─────────────────────────────────────────────────────────────────────────────
-- CineAmman — Seed: Cinemas
-- Run AFTER 001_schema.sql
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO cinemas
  (name_en, name_ar, slug, mall_name_en, mall_name_ar, address_en, address_ar,
   google_maps_url, website_url, scraper_url, active)
VALUES

-- 1. Grand Cinemas — City Mall
(
  'Grand Cinemas City Mall',
  'غراند سينما سيتي مول',
  'grand-cinemas-city-mall',
  'City Mall',
  'سيتي مول',
  'City Mall, Al-Jubeiha, Amman, Jordan',
  'سيتي مول، الجبيهة، عمان، الأردن',
  'https://maps.google.com/?q=City+Mall+Amman',
  'https://www.grandcinemas.com',
  'https://www.grandcinemas.com/jordan/en/showtimes',
  true
),

-- 2. Grand Cinemas — Abdali Mall
(
  'Grand Cinemas Abdali Mall',
  'غراند سينما مول العبدلي',
  'grand-cinemas-abdali-mall',
  'Abdali Mall',
  'مول العبدلي',
  'Abdali Mall, Downtown Amman, Jordan',
  'مول العبدلي، وسط البلد، عمان، الأردن',
  'https://maps.google.com/?q=Abdali+Mall+Amman',
  'https://www.grandcinemas.com',
  'https://www.grandcinemas.com/jordan/en/showtimes',
  true
),

-- 3. Reel Cinemas — Taj Mall
(
  'Reel Cinemas Taj Mall',
  'ريل سينما تاج مول',
  'reel-cinemas-taj-mall',
  'Taj Mall',
  'تاج مول',
  'Taj Mall, Tla'' Al-Ali, Amman, Jordan',
  'تاج مول، تلاع العلي، عمان، الأردن',
  'https://maps.google.com/?q=Taj+Mall+Amman',
  'https://www.reelcinemas.ae',
  'https://www.reelcinemas.ae/en/movies',
  true
),

-- 4. Prime Cinemas
(
  'Prime Cinemas',
  'برايم سينما',
  'prime-cinemas',
  'Al-Baraka Mall',
  'مول البركة',
  'Al-Baraka Mall, Amman, Jordan',
  'مول البركة، عمان، الأردن',
  'https://maps.google.com/?q=Prime+Cinemas+Amman',
  NULL,
  'https://www.primecinemas.jo',
  false  -- scraper_url not yet confirmed; set active=false until verified
);
