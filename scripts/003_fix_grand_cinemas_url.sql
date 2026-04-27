-- Fix Grand Cinemas scraper URL to the correct Jordan domain
-- Run in: Supabase → SQL Editor → New query → Paste → Run

UPDATE cinemas
SET
  scraper_url = 'https://jo.grandcinemasme.com/',
  website_url = 'https://jo.grandcinemasme.com',
  active = true
WHERE slug IN ('grand-cinemas-city-mall', 'grand-cinemas-abdali-mall');

-- Confirm the update
SELECT slug, name_en, scraper_url, active FROM cinemas;
