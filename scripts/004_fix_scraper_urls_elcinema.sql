-- Switch all cinemas to use elcinema.com as the data source
-- Run in: Supabase → SQL Editor → New query → Paste → Run

UPDATE cinemas SET
  scraper_url = 'https://elcinema.com/en/theater/3101322/',
  active = true
WHERE slug = 'grand-cinemas-city-mall';

UPDATE cinemas SET
  scraper_url = 'https://elcinema.com/en/theater/3101465/',
  active = true
WHERE slug = 'grand-cinemas-abdali-mall';

UPDATE cinemas SET
  scraper_url = 'https://elcinema.com/en/theater/3101517/',
  active = true
WHERE slug = 'reel-cinemas-taj-mall';

UPDATE cinemas SET
  scraper_url = 'https://elcinema.com/en/theater/3101467/',
  active = true
WHERE slug = 'prime-cinemas';

-- Confirm
SELECT slug, name_en, scraper_url, active FROM cinemas ORDER BY name_en;
