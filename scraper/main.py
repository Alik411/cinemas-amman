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

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'), encoding='utf-8-sig', override=True)

ANTHROPIC_API_KEY   = os.environ['ANTHROPIC_API_KEY']
SUPABASE_URL        = os.environ['NEXT_PUBLIC_SUPABASE_URL']
SUPABASE_KEY        = os.environ['SUPABASE_SERVICE_ROLE_KEY']
TMDB_API_KEY        = os.environ.get('TMDB_API_KEY', '')

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
# Poster helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_poster_map(html: str) -> dict[str, str]:
    """
    Parses elcinema AJAX HTML and returns {movie_title_lower: poster_url}.
    Keys include both English and Arabic titles (elcinema uses whichever language
    the movie was registered in), so lookups must try both title_en and title_ar.
    HTML entities like &#39; are unescaped before storing keys.
    """
    import html as html_module
    poster_map: dict[str, str] = {}
    blocks = re.findall(
        r'<a href="/work/(\d+)/"><img[^>]+data-src="([^"]+)"[^>]*/></a>'
        r'.*?<h3><a href="/work/\1/">([^<]+)</a>',
        html,
        re.DOTALL,
    )
    for _work_id, poster_url, title in blocks:
        # Upgrade from 150x200 thumbnail to a larger size
        poster_url = poster_url.replace('_150x200_', '_310x413_')
        # Unescape HTML entities (e.g. &#39; → ')
        clean_title = html_module.unescape(title.strip())
        poster_map[clean_title.lower()] = poster_url
    return poster_map


async def fetch_tmdb_poster(title_en: str) -> str | None:
    """Searches TMDB for a movie and returns its poster URL, or None."""
    import aiohttp
    if not TMDB_API_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                'https://api.themoviedb.org/3/search/movie',
                params={'query': title_en, 'language': 'en-US', 'page': 1},
                headers={'Authorization': f'Bearer {TMDB_API_KEY}', 'accept': 'application/json'},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get('results', [])
                    if results and results[0].get('poster_path'):
                        return f"https://image.tmdb.org/t/p/w500{results[0]['poster_path']}"
    except Exception as e:
        err = str(e).encode('ascii', errors='replace').decode('ascii')
        print(f'  WARN TMDB lookup failed for "{title_en}": {err}')
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Scrape HTML from cinema website
# ─────────────────────────────────────────────────────────────────────────────

async def scrape_cinema(cinema: dict) -> str | None:
    """
    Visits the cinema's scraper_url with Playwright to get the CSRF token,
    then directly POSTs to elcinema's AJAX endpoint to fetch the showtimes HTML.
    Returns the combined page HTML + showtime HTML, or None on failure.
    """
    import aiohttp
    from datetime import timedelta
    url = cinema['scraper_url']
    name = cinema['name_en']
    today = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%Y-%m-%d')

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
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        # Block heavy third-party resources to load faster
        async def block_route(route):
            u = route.request.url
            if any(x in u for x in [
                '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg',
                '.woff', '.woff2', '.ttf', 'doubleclick', 'googlesyndication',
                'google-analytics', 'googletagmanager', 'inmobi', 'tashop',
                'justwatch', 'twitter.com/widgets',
            ]):
                await route.abort()
            else:
                await route.continue_()

        await page.route('**/*', block_route)

        try:
            print(f'  >> Visiting {url}')
            await page.goto(url, timeout=60_000, wait_until='load')
            await asyncio.sleep(1.5)

            # Get CSRF token and theater ID from the page
            csrf_token = await page.locator('meta[name="csrf-token"]').get_attribute('content')
            theater_id = await page.locator('#theater-showtimes-date-selector').get_attribute('data-id')

            if not csrf_token or not theater_id:
                # Fallback: return plain page HTML (non-elcinema pages)
                html = await page.content()
                print(f'  OK Got {len(html):,} chars from {name} (no AJAX endpoint found)')
                return html

            # Get cookies from Playwright context for the AJAX request
            cookies = await context.cookies()
            cookie_header = '; '.join(f'{c["name"]}={c["value"]}' for c in cookies)

            print(f'  >> Calling AJAX endpoint for theater {theater_id}, date {today}')

            # Make the POST request directly (much faster than waiting for Playwright to do it)
            ajax_html = None
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://elcinema.com/theater/ajax_show',
                    data={'date': today, 'id': theater_id},
                    headers={
                        'X-CSRF-Token': csrf_token,
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Referer': url,
                        'Origin': 'https://elcinema.com',
                        'Cookie': cookie_header,
                        'User-Agent': random.choice(USER_AGENTS),
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        ajax_html = await resp.text()
                        print(f'  >> AJAX returned {len(ajax_html):,} chars of showtime HTML')
                    else:
                        print(f'  WARN AJAX returned status {resp.status}')

            await browser.close()

            if ajax_html and len(ajax_html) > 200:
                return ajax_html  # This is the pure showtime HTML — send directly to Claude
            else:
                print(f'  WARN AJAX returned empty/small response — no showtimes today?')
                return None

        except PlaywrightTimeout:
            print(f'  ERR Timeout loading {name} ({url})')
            await browser.close()
            return None
        except Exception as e:
            err = str(e).encode('ascii', errors='replace').decode('ascii')
            print(f'  ERR Error loading {name}: {err}')
            await browser.close()
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Parse HTML into structured showtimes using Claude
# ─────────────────────────────────────────────────────────────────────────────

CHUNK_SIZE = 180_000  # chars per Claude call


async def _call_claude_for_chunk(chunk: str, cinema_name: str, today: str, chunk_num: int) -> list[dict]:
    """Calls Claude on one chunk of HTML and returns extracted showtimes."""
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
- If no showtimes can be found in this chunk, return [].
- Do not invent data.

HTML (chunk {chunk_num}):
{chunk}"""

    response = await anthropic_client.messages.create(
        model='claude-sonnet-4-5',
        max_tokens=16000,
        system='You are a data extraction assistant. Extract cinema showtime data from HTML and return ONLY valid JSON, no other text.',
        messages=[{'role': 'user', 'content': prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    result = json.loads(raw)
    return result if isinstance(result, list) else []


async def parse_with_claude(html: str, cinema_name: str) -> list[dict]:
    """
    Splits the HTML into chunks and calls Claude on each chunk to extract
    showtimes. Merges all results, deduplicating by (title, date, time).
    """
    from datetime import timedelta
    today = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%Y-%m-%d')

    # Split into overlapping chunks so we don't miss data at boundaries
    chunks = []
    overlap = 5_000  # chars of overlap between chunks
    start = 0
    while start < len(html):
        end = min(start + CHUNK_SIZE, len(html))
        chunks.append(html[start:end])
        if end == len(html):
            break
        start = end - overlap

    print(f'  >> Sending {len(html):,} chars in {len(chunks)} chunk(s) to Claude')

    all_showtimes: list[dict] = []
    seen: set[tuple] = set()

    for i, chunk in enumerate(chunks, 1):
        try:
            results = await _call_claude_for_chunk(chunk, cinema_name, today, i)
            new_count = 0
            for st in results:
                key = (
                    st.get('movie_title_en', '').lower().strip(),
                    st.get('show_date', ''),
                    st.get('show_time', ''),
                    st.get('screen_type', '2D'),
                )
                if key[0] and key not in seen:
                    seen.add(key)
                    all_showtimes.append(st)
                    new_count += 1
            print(f'  OK Chunk {i}/{len(chunks)}: {len(results)} raw, {new_count} new unique showtimes')
            if len(chunks) > 1:
                await asyncio.sleep(0.5)
        except json.JSONDecodeError as e:
            print(f'  ERR Chunk {i} returned invalid JSON: {e}')
        except Exception as e:
            err = str(e).encode('ascii', errors='replace').decode('ascii')
            print(f'  ERR Chunk {i} Claude error: {err}')

    print(f'  OK Total: {len(all_showtimes)} unique showtimes extracted')
    return all_showtimes


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
    poster_map: dict[str, str] | None = None,
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

    # Load all existing movies: slug→id, title_ar_lower→id
    movie_slug_to_id: dict[str, str] = {}
    movie_ar_to_id:   dict[str, str] = {}
    existing_slugs:   set[str]       = set()
    try:
        res = supabase.table('movies').select('id, slug, title_ar, poster_url').execute()
        for row in res.data:
            movie_slug_to_id[row['slug']] = row['id']
            existing_slugs.add(row['slug'])
            if row.get('title_ar'):
                movie_ar_to_id[row['title_ar'].strip().lower()] = row['id']
    except Exception as e:
        print(f'  ERR Could not fetch existing movies: {e}')

    poster_map = poster_map or {}

    new_movies = 0
    for title_en, raw_st in seen_titles.items():
        slug = slugify(title_en)
        title_ar_raw = (raw_st.get('movie_title_ar') or '').strip()

        # Check if this movie already exists under a different English transliteration
        # by matching on the Arabic title (prevents Saffah/Saffah duplicates)
        if slug not in existing_slugs and title_ar_raw:
            existing_id = movie_ar_to_id.get(title_ar_raw.lower())
            if existing_id:
                # Already exists — just reuse the existing movie ID
                movie_slug_to_id[slug] = existing_id
                print(f'  >> Matched "{title_en}" to existing movie via Arabic title')
                # Don't create a new movie row — fall through to showtime insert
                slug = next(s for s, i in movie_slug_to_id.items() if i == existing_id)

        # Resolve poster: try English title, then Arabic title from elcinema map, then TMDB
        poster_url = (
            poster_map.get(title_en.lower()) or
            (poster_map.get(title_ar_raw.lower()) if title_ar_raw else None)
        )
        if not poster_url:
            poster_url = await fetch_tmdb_poster(title_en)
            if poster_url:
                print(f'  >> TMDB poster found for: {title_en}')

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
                'poster_url':   poster_url,
                'enriched_at':  datetime.now(timezone.utc).isoformat(),
            }
            try:
                res = supabase.table('movies').upsert(movie_row, on_conflict='slug').execute()
                movie_slug_to_id[slug] = res.data[0]['id']
                new_movies += 1
            except Exception as e:
                print(f'  ERR Failed to upsert movie "{title_en}": {e}')
        else:
            # Movie exists — backfill poster if it's missing
            movie_id = movie_slug_to_id.get(slug)
            if movie_id and poster_url:
                try:
                    # Only update if poster_url is currently null
                    supabase.table('movies').update({'poster_url': poster_url})\
                        .eq('id', movie_id).is_('poster_url', 'null').execute()
                except Exception:
                    pass

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
    import traceback
    print(f'\n{"="*50}')
    print(f'Cinema: {cinema["name_en"]}')

    start = time.time()

    try:
        html = await scrape_cinema(cinema)
        if not html:
            handle_scrape_failure(cinema, 'Failed to load page (timeout or bot block)', start)
            return

        # Basic bot-detection check: if the page is tiny it's probably a block page
        if len(html) < 2_000:
            handle_scrape_failure(cinema, f'Suspiciously small response ({len(html)} bytes) — possible bot block', start)
            return

        # Extract poster URLs from the raw HTML before sending to Claude
        poster_map = extract_poster_map(html)
        if poster_map:
            print(f'  >> Found {len(poster_map)} poster(s) in HTML')

        showtimes = await parse_with_claude(html, cinema['name_en'])
        await save_to_supabase(showtimes, cinema, start, poster_map)
    except Exception:
        traceback.print_exc()


async def run_all_scrapers() -> None:
    print('=' * 50)
    print('CineAmman Scraper starting...')
    from datetime import timedelta
    jordan_time = datetime.now(timezone.utc) + timedelta(hours=3)
    today_jordan = jordan_time.strftime('%Y-%m-%d')
    print(f'Time: {jordan_time.strftime("%Y-%m-%d %H:%M")} Amman')
    print('=' * 50)

    # Clean up showtimes older than today
    try:
        supabase.table('showtimes').delete().lt('show_date', today_jordan).execute()
        print(f'Cleaned up old showtimes before {today_jordan}')
    except Exception as e:
        print(f'WARN Could not clean old showtimes: {e}')

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
            err_str = str(e).encode('ascii', errors='replace').decode('ascii')
            print(f'  ERR Unexpected error for {cinema["name_en"]}: {err_str}')

    print(f'\n{"="*50}')
    print('All scrapers finished.')
    print('=' * 50)


if __name__ == '__main__':
    asyncio.run(run_all_scrapers())
