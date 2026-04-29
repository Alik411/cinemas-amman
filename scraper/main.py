"""
CineAmman Scraper
Fetches showtimes from Amman cinema websites, parses them with Claude,
enriches movie data, and saves everything to Supabase.
"""

import asyncio
import json
import os
import random
import re
import time
from datetime import datetime, timezone

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from supabase import create_client, Client

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'), encoding='utf-8-sig')

ANTHROPIC_API_KEY   = os.environ['ANTHROPIC_API_KEY']
SUPABASE_URL        = os.environ['NEXT_PUBLIC_SUPABASE_URL']
SUPABASE_KEY        = os.environ['SUPABASE_SERVICE_ROLE_KEY']

anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
]

# How many consecutive failures before we mark a cinema inactive
FAILURE_THRESHOLD = 3


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Scrape HTML from cinema website
# ─────────────────────────────────────────────────────────────────────────────

async def scrape_cinema(cinema: dict) -> str | None:
    """
    Visits the cinema's scraper_url with Playwright (headless Chromium),
    waits for content to load, and returns the full page HTML.
    Returns None on failure.
    """
    url = cinema['scraper_url']
    name = cinema['name_en']

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ],
        )
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={'width': 1280, 'height': 800},
            locale='en-US',
            timezone_id='Asia/Amman',
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'DNT': '1',
            },
        )
        # Hide webdriver property
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        # Block images/fonts to speed up loading
        await page.route('**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}',
                         lambda route: route.abort())

        try:
            print(f'  >> Visiting {url}')
            await page.goto(url, timeout=60_000, wait_until='networkidle')

            # Extra wait for JS-rendered content
            await asyncio.sleep(random.uniform(2.0, 4.0))

            # Scroll down to trigger lazy-loading
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight / 2)')
            await asyncio.sleep(1.5)
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(1.5)

            # Wait for any of these common showtime container selectors
            selectors = [
                '[class*="showtime"]', '[class*="movie"]', '[class*="schedule"]',
                '[class*="film"]',     '[id*="showtime"]',  '[id*="movie"]',
                'table',               '.listing',          '.content', 'main',
            ]
            for sel in selectors:
                try:
                    await page.wait_for_selector(sel, timeout=5_000)
                    break
                except PlaywrightTimeout:
                    continue

            html = await page.content()
            print(f'  OK Got {len(html):,} bytes from {name}')
            return html

        except PlaywrightTimeout:
            print(f'  ERR Timeout loading {name} ({url})')
            return None
        except Exception as e:
            print(f'  ERR Error loading {name}: {e}')
            return None
        finally:
            await browser.close()


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Parse HTML into structured showtimes using Claude
# ─────────────────────────────────────────────────────────────────────────────

async def parse_with_claude(html: str, cinema_name: str) -> list[dict]:
    """
    Sends the raw HTML to Claude and gets back a structured JSON array
    of showtime objects.
    """
    # Send up to 150k chars — elcinema pages are 400-450k but showtimes are in the first portion
    html_snippet = html[:150_000]

    from datetime import timedelta
    today = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%Y-%m-%d')
    prompt = f"""Extract all movie showtimes from this cinema website HTML for {cinema_name}.

This page is from elcinema.com — an Arabic cinema listings site.
Movie titles may appear in English, Arabic, or both.
Times may appear as "2:00 PM" or "14:00" — convert all to 24-hour HH:MM format.
Dates may appear as day names ("Today", "Monday", "الاثنين") — today is {today}.

Return a JSON array where each object has exactly these keys:
- movie_title_en: string (English title — if only Arabic is present, transliterate it)
- movie_title_ar: string or null (Arabic title if present)
- show_date: string in YYYY-MM-DD format
- show_time: string in HH:MM 24-hour format
- screen_type: exactly one of "2D", "3D", "IMAX", "4DX" (default "2D" if unclear)
- language: exactly one of "English", "Arabic", "Dubbed" (default "English"; use "Arabic" if the movie is in Arabic)
- booking_url: string or null

Rules:
- Return ONLY the JSON array, no explanation, no markdown code fences.
- Create one object per showtime (one movie at 3 times = 3 objects).
- If no showtimes can be found, return [].
- Do not invent data.

HTML:
{html_snippet}"""

    try:
        response = await anthropic_client.messages.create(
            model='claude-sonnet-4-5',
            max_tokens=8096,
            system='You are a data extraction assistant. Extract cinema showtime data from HTML and return ONLY valid JSON, no other text.',
            messages=[{'role': 'user', 'content': prompt}],
        )

        raw = response.content[0].text.strip()

        # Strip markdown code fences if Claude added them despite instructions
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        showtimes = json.loads(raw)
        print(f'  OK Claude extracted {len(showtimes)} showtimes')
        return showtimes if isinstance(showtimes, list) else []

    except json.JSONDecodeError as e:
        print(f'  ERR Claude returned invalid JSON: {e}')
        return []
    except Exception as e:
        print(f'  ERR Claude API error: {e}')
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Enrich new movies with Claude
# ─────────────────────────────────────────────────────────────────────────────

async def enrich_movie_with_claude(title_en: str) -> dict:
    """
    For movies not yet in the database, asks Claude to fill in
    Arabic title, synopsis, genres, rating, and duration.
    """
    prompt = f"""For the movie "{title_en}", provide the following information.
Return ONLY a JSON object with exactly these keys, no other text:
- title_ar: Arabic translation/transliteration of the title (string)
- synopsis_en: an 80-word English synopsis (string)
- synopsis_ar: an 80-word Arabic synopsis (string)
- genre_tags: array of 2-4 genre strings, e.g. ["Action", "Adventure"]
- age_rating: one of "G", "PG", "PG-13", "R", "NR" (string)
- duration_mins: approximate runtime as an integer, or null if unknown

If the movie is not well-known, make reasonable estimates based on the title."""

    try:
        response = await anthropic_client.messages.create(
            model='claude-sonnet-4-5',
            max_tokens=1024,
            system='You are a movie database assistant. Return only valid JSON.',
            messages=[{'role': 'user', 'content': prompt}],
        )

        raw = response.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        data = json.loads(raw)
        print(f'  OK Enriched: {title_en}')
        return data

    except Exception as e:
        print(f'  ERR Failed to enrich "{title_en}": {e}')
        return {
            'title_ar': None,
            'synopsis_en': None,
            'synopsis_ar': None,
            'genre_tags': [],
            'age_rating': 'NR',
            'duration_mins': None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Converts a movie title to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')


def get_consecutive_failures(cinema_id: str) -> int:
    """Counts how many consecutive failures this cinema has had recently."""
    try:
        result = (
            supabase.table('scraper_logs')
            .select('status')
            .eq('cinema_id', cinema_id)
            .order('ran_at', desc=True)
            .limit(FAILURE_THRESHOLD)
            .execute()
        )
        logs = result.data
        if not logs:
            return 0
        return sum(1 for log in logs if log['status'] == 'failed')
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Save to Supabase
# ─────────────────────────────────────────────────────────────────────────────

async def save_to_supabase(
    showtimes: list[dict],
    cinema: dict,
    start_time: float,
) -> None:
    """
    Upserts movies, inserts showtimes, and writes a scraper_log entry.
    """
    if not showtimes:
        supabase.table('scraper_logs').insert({
            'cinema_id':       cinema['id'],
            'status':          'partial',
            'showtimes_found': 0,
            'movies_found':    0,
            'error_message':   'No showtimes found in HTML',
            'duration_ms':     int((time.time() - start_time) * 1000),
        }).execute()
        return

    # Collect unique movie titles
    seen_titles: dict[str, dict] = {}
    for st in showtimes:
        title = st.get('movie_title_en', '').strip()
        if title and title not in seen_titles:
            seen_titles[title] = st

    # Check which movies are already in the DB
    existing_slugs: set[str] = set()
    try:
        res = supabase.table('movies').select('slug').execute()
        existing_slugs = {row['slug'] for row in res.data}
    except Exception as e:
        print(f'  ERR Could not fetch existing movies: {e}')

    # Enrich and upsert new movies
    movie_slug_to_id: dict[str, str] = {}

    # Fetch IDs for movies already in DB
    if existing_slugs:
        res = supabase.table('movies').select('id, slug').execute()
        for row in res.data:
            movie_slug_to_id[row['slug']] = row['id']

    new_movies = 0
    for title_en, raw_st in seen_titles.items():
        slug = slugify(title_en)

        if slug not in existing_slugs:
            print(f'  >> Enriching new movie: {title_en}')
            enriched = await enrich_movie_with_claude(title_en)
            await asyncio.sleep(0.5)  # brief pause between Claude calls

            movie_row = {
                'title_en':     title_en,
                'title_ar':     raw_st.get('movie_title_ar') or enriched.get('title_ar'),
                'slug':         slug,
                'synopsis_en':  enriched.get('synopsis_en'),
                'synopsis_ar':  enriched.get('synopsis_ar'),
                'genre_tags':   enriched.get('genre_tags', []),
                'age_rating':   enriched.get('age_rating'),
                'duration_mins':enriched.get('duration_mins'),
                'enriched_at':  datetime.now(timezone.utc).isoformat(),
            }
            try:
                res = supabase.table('movies').upsert(movie_row, on_conflict='slug').execute()
                movie_slug_to_id[slug] = res.data[0]['id']
                new_movies += 1
            except Exception as e:
                print(f'  ERR Failed to upsert movie "{title_en}": {e}')
        else:
            if slug not in movie_slug_to_id:
                res = supabase.table('movies').select('id').eq('slug', slug).execute()
                if res.data:
                    movie_slug_to_id[slug] = res.data[0]['id']

    # Insert showtimes (ignore duplicates via UNIQUE constraint)
    inserted = 0
    for st in showtimes:
        title = st.get('movie_title_en', '').strip()
        slug = slugify(title)
        movie_id = movie_slug_to_id.get(slug)
        if not movie_id:
            continue

        show_date = st.get('show_date')
        show_time = st.get('show_time')
        if not show_date or not show_time:
            continue

        try:
            supabase.table('showtimes').upsert({
                'movie_id':    movie_id,
                'cinema_id':   cinema['id'],
                'show_date':   show_date,
                'show_time':   show_time,
                'screen_type': st.get('screen_type', '2D'),
                'language':    st.get('language', 'English'),
                'booking_url': st.get('booking_url'),
            }, on_conflict='movie_id,cinema_id,show_date,show_time,screen_type,language').execute()
            inserted += 1
        except Exception as e:
            print(f'  ERR Showtime insert error: {e}')

    duration_ms = int((time.time() - start_time) * 1000)
    supabase.table('scraper_logs').insert({
        'cinema_id':       cinema['id'],
        'status':          'success',
        'showtimes_found': inserted,
        'movies_found':    new_movies,
        'duration_ms':     duration_ms,
    }).execute()

    print(f'  OK Saved {inserted} showtimes, {new_movies} new movies ({duration_ms}ms)')


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 (fallback): Deactivate persistently failing cinemas
# ─────────────────────────────────────────────────────────────────────────────

def handle_scrape_failure(cinema: dict, error_message: str, start_time: float) -> None:
    """Logs a failure and deactivates the cinema if it keeps failing."""
    duration_ms = int((time.time() - start_time) * 1000)
    supabase.table('scraper_logs').insert({
        'cinema_id':     cinema['id'],
        'status':        'failed',
        'error_message': error_message,
        'duration_ms':   duration_ms,
    }).execute()

    failures = get_consecutive_failures(cinema['id'])
    if failures >= FAILURE_THRESHOLD:
        supabase.table('cinemas').update({'active': False}).eq('id', cinema['id']).execute()
        print(f'  WARN {cinema["name_en"]} deactivated after {failures} consecutive failures')


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

async def run_scraper_for_cinema(cinema: dict) -> None:
    print(f'\n{"="*50}')
    print(f'Cinema: {cinema["name_en"]}')

    start = time.time()

    html = await scrape_cinema(cinema)
    if not html:
        handle_scrape_failure(cinema, 'Failed to load page (timeout or bot block)', start)
        return

    # Basic bot-detection check: if the page is tiny it's probably a block page
    if len(html) < 2_000:
        handle_scrape_failure(cinema, f'Suspiciously small response ({len(html)} bytes) — possible bot block', start)
        return

    showtimes = await parse_with_claude(html, cinema['name_en'])
    await save_to_supabase(showtimes, cinema, start)


async def run_all_scrapers() -> None:
    print('=' * 50)
    print('CineAmman Scraper starting...')
    from datetime import timedelta
    jordan_time = datetime.now(timezone.utc) + timedelta(hours=3)
    print(f'Time: {jordan_time.strftime("%Y-%m-%d %H:%M")} Amman')
    print('=' * 50)

    result = supabase.table('cinemas').select('*').eq('active', True).execute()
    cinemas = result.data

    if not cinemas:
        print('No active cinemas found in database.')
        return

    print(f'Found {len(cinemas)} active cinema(s)')

    for cinema in cinemas:
        try:
            await run_scraper_for_cinema(cinema)
        except Exception as e:
            print(f'  ERR Unexpected error for {cinema["name_en"]}: {e}')

    print(f'\n{"="*50}')
    print('All scrapers finished.')
    print('=' * 50)


if __name__ == '__main__':
    asyncio.run(run_all_scrapers())
