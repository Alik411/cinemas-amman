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
FAILURE_THRESHOLD = 7


# ─────────────────────────────────────────────────────────────────────────────
# Poster helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_elcinema_data(html: str) -> dict[int, dict]:
    """
    Parses elcinema AJAX HTML and returns {work_id: {title, poster_url}}.
    The work_id is elcinema's stable numeric identifier for each movie —
    the single most reliable deduplication key we have.
    """
    import html as html_module
    result: dict[int, dict] = {}
    blocks = re.findall(
        r'<a href="/work/(\d+)/"><img[^>]+data-src="([^"]+)"[^>]*/></a>'
        r'.*?<h3><a href="/work/\1/">([^<]+)</a>',
        html,
        re.DOTALL,
    )
    for work_id_str, poster_url, title in blocks:
        clean_title = html_module.unescape(title.strip())
        result[int(work_id_str)] = {
            'title': clean_title,
            'poster_url': poster_url,  # kept for reference but not used for display
        }
    return result


def extract_poster_map(html: str) -> dict[str, str]:
    """
    Returns {title_lower: poster_url} for backward-compatible poster lookup.
    """
    data = extract_elcinema_data(html)
    return {v['title'].lower(): v['poster_url'] for v in data.values()}


def extract_date_mapping(html: str) -> dict[str, str]:
    """
    Extracts the date selector options from elcinema HTML.
    Returns {arabic_label: 'YYYY-MM-DD'}, e.g. {'الخميس 30 ابريل': '2026-04-30'}.
    This lets Claude correctly assign dates to showtimes based on section headers.
    """
    import html as html_module
    mapping: dict[str, str] = {}
    for date_val, label in re.findall(
        r'<option value="(\d{4}-\d{2}-\d{2})"[^>]*>\s*([^<]+?)\s*</option>', html
    ):
        clean = html_module.unescape(label.strip())
        mapping[clean] = date_val
    return mapping


async def fetch_tmdb_data(title_en: str) -> dict | None:
    """
    Searches TMDB for a movie and returns a dict with poster_url, synopsis_en,
    genre_tags, duration_mins, and age_rating. Returns None if not found.
    """
    import aiohttp
    if not TMDB_API_KEY:
        return None
    try:
        headers = {'Authorization': f'Bearer {TMDB_API_KEY}', 'accept': 'application/json'}
        async with aiohttp.ClientSession() as session:
            # Step 1: search for the movie
            async with session.get(
                'https://api.themoviedb.org/3/search/movie',
                params={'query': title_en, 'language': 'en-US', 'page': 1},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                results = data.get('results', [])
                if not results:
                    return None
                movie = results[0]

            movie_id = movie.get('id')
            poster_path = movie.get('poster_path')
            overview = movie.get('overview', '')

            # Step 2: fetch full details (runtime + release dates for rating)
            runtime = None
            age_rating = 'NR'
            genre_names: list[str] = []
            if movie_id:
                async with session.get(
                    f'https://api.themoviedb.org/3/movie/{movie_id}',
                    params={'language': 'en-US', 'append_to_response': 'release_dates'},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as detail_resp:
                    if detail_resp.status == 200:
                        detail = await detail_resp.json()
                        runtime = detail.get('runtime') or None
                        genre_names = [g['name'] for g in detail.get('genres', [])]
                        # Find US rating
                        for entry in (detail.get('release_dates', {}).get('results') or []):
                            if entry.get('iso_3166_1') == 'US':
                                for rd in entry.get('release_dates', []):
                                    cert = rd.get('certification', '').strip()
                                    if cert:
                                        age_rating = cert
                                        break
                                break

            return {
                'tmdb_id':       movie_id,
                'poster_url':    f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
                'synopsis_en':   overview if overview else None,
                'genre_tags':    genre_names,
                'duration_mins': runtime,
                'age_rating':    age_rating,
            }
    except Exception as e:
        err = str(e).encode('ascii', errors='replace').decode('ascii')
        print(f'  WARN TMDB lookup failed for "{title_en}": {err}')
    return None


async def fetch_tmdb_poster(title_en: str) -> str | None:
    """Backward-compatible wrapper — returns just the poster URL."""
    data = await fetch_tmdb_data(title_en)
    return data['poster_url'] if data else None


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Scrape HTML from cinema website
# ─────────────────────────────────────────────────────────────────────────────

async def scrape_taj_cinemas(cinema: dict) -> list[dict] | None:
    """
    Scrapes tajcinemas.com directly — no Claude needed, all data is server-rendered.
    Fetches the homepage for movie IDs, then each movie page for dates + showtimes.

    Key insight: date_id is embedded in every booking URL
    (/movies/982/book/748/46788 → date_id=748), so we never need to
    split the page into date sections — we extract ALL booking links at once
    and group them by date_id.
    """
    import aiohttp
    from datetime import timedelta

    today = datetime.now(timezone.utc) + timedelta(hours=3)
    today_str = today.strftime('%Y-%m-%d')
    max_date_str = (today + timedelta(days=7)).strftime('%Y-%m-%d')

    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    try:
        async with aiohttp.ClientSession() as session:
            # ── Step 1: fetch homepage ──────────────────────────────────────────
            async with session.get(
                'https://tajcinemas.com/', headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    print(f'  ERR HTTP {resp.status} from Taj Cinemas homepage')
                    return None
                homepage_html = await resp.text()

            # Detect where the "Taj Class" section starts in the homepage
            # (movies after this marker use 'Taj Class' as screen_type)
            hplow = homepage_html.lower()
            taj_class_pos = hplow.find('taj class')
            if taj_class_pos == -1:
                taj_class_pos = homepage_html.find('id="hot"')

            # Extract all movie IDs — try absolute URLs first, then relative
            movie_ids_seen: set[str] = set()
            movies_info: list[dict] = []

            # Try both absolute (tajcinemas.com/movies/NNN) and relative (/movies/NNN)
            for pattern in (r'tajcinemas\.com/movies/(\d+)', r'href=["\'][^"\']*?/movies/(\d+)'):
                for m in re.finditer(pattern, homepage_html):
                    mid = m.group(1)
                    if mid in movie_ids_seen:
                        continue
                    movie_ids_seen.add(mid)
                    # Get 200-char context around the link to check for TAJCLASS suffix
                    ctx = homepage_html[max(0, m.start()-50): m.end()+200].lower()
                    is_taj = (
                        'tajclass' in ctx
                        or (taj_class_pos > 0 and m.start() > taj_class_pos)
                    )
                    movies_info.append({'id': mid, 'is_taj_class': is_taj})
                if movies_info:
                    break  # found movies — don't try the second pattern

            if not movies_info:
                print(f'  WARN No movies found on Taj Cinemas homepage')
                return None

            print(f'  >> Found {len(movies_info)} movie(s) on tajcinemas.com')

            all_showtimes: list[dict] = []

            # ── Step 2: for each movie, fetch its page and extract showtimes ───
            for info in movies_info:
                movie_id    = info['id']
                screen_type = 'Taj Class' if info['is_taj_class'] else '2D'

                await asyncio.sleep(0.3)

                async with session.get(
                    f'https://tajcinemas.com/movies/{movie_id}',
                    headers=headers, timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        continue
                    movie_html = await resp.text()

                # ── Extract title ───────────────────────────────────────────────
                title_en = None
                # Try <title> tag first (most reliable)
                t = re.search(r'<title[^>]*>\s*([^<|–\-]+?)[\s|–\-]*(?:Taj|$)', movie_html, re.IGNORECASE)
                if t:
                    title_en = t.group(1).strip()
                # Fallback: first non-trivial <h1> or <h2>
                if not title_en:
                    for tag in ('h1', 'h2', 'h3'):
                        for h in re.findall(rf'<{tag}[^>]*>\s*([^<]{{3,80}})\s*</{tag}>', movie_html, re.IGNORECASE):
                            candidate = h.strip()
                            if candidate.upper() not in ('TAJ', 'TAJ CLASS', 'NOW SHOWING', ''):
                                title_en = candidate
                                break
                        if title_en:
                            break
                if not title_en:
                    continue

                # Clean up: decode HTML entities, remove -TAJCLASS suffix, fix casing
                import html as html_module
                title_en = html_module.unescape(title_en)
                title_en = re.sub(r'[-\s]*TAJCLASS\s*$', '', title_en, flags=re.IGNORECASE).strip()
                if title_en == title_en.upper():
                    title_en = title_en.title()

                # ── Build date_id → YYYY-MM-DD from the tab navigation ─────────
                # HTML: <a href="#date-748">Sun\n    17</a>
                date_id_to_date: dict[str, str] = {}
                for dm in re.finditer(r'href="#date-(\d+)"[^>]*>([\s\S]{0,120}?)</a', movie_html, re.IGNORECASE):
                    date_id   = dm.group(1)
                    tab_inner = dm.group(2)
                    day_m     = re.search(r'(\d{1,2})', tab_inner)
                    if not day_m:
                        continue
                    day = int(day_m.group(1))
                    try:
                        candidate = today.replace(day=day)
                        if candidate.date() < (today - timedelta(days=1)).date():
                            raise ValueError('past')
                    except ValueError:
                        # Month rollover
                        m_ = today.month + 1 if today.month < 12 else 1
                        y_ = today.year if today.month < 12 else today.year + 1
                        try:
                            candidate = today.replace(year=y_, month=m_, day=day)
                        except ValueError:
                            continue
                    date_str = candidate.strftime('%Y-%m-%d')
                    if today_str <= date_str <= max_date_str:
                        date_id_to_date[date_id] = date_str

                if not date_id_to_date:
                    continue

                # ── Extract ALL booking links (date_id is in the URL itself) ────
                # href="/movies/982/book/748/46788" → date_id=748, session_id=46788
                # href text (inner) → time like "16:00"
                count_before = len(all_showtimes)
                for bm in re.finditer(
                    rf'href=["\'](?:https://tajcinemas\.com)?/movies/{movie_id}/book/(\d+)/(\d+)["\'][^>]*>\s*(\d{{2}}:\d{{2}})\s*<',
                    movie_html,
                ):
                    date_id    = bm.group(1)
                    session_id = bm.group(2)
                    time_str   = bm.group(3)
                    show_date  = date_id_to_date.get(date_id)
                    if not show_date:
                        continue
                    all_showtimes.append({
                        'movie_title_en': title_en,
                        'movie_title_ar':  None,
                        'show_date':       show_date,
                        'show_time':       time_str,
                        'screen_type':     screen_type,
                        'language':        'English',
                        'booking_url':     f'https://tajcinemas.com/movies/{movie_id}/book/{date_id}/{session_id}',
                    })
                print(f'  >> {title_en}: {len(all_showtimes) - count_before} showtimes across {len(date_id_to_date)} date(s)')

            print(f'  >> Extracted {len(all_showtimes)} showtime(s) from tajcinemas.com')
            return all_showtimes if all_showtimes else None

    except Exception as e:
        err = str(e).encode('ascii', errors='replace').decode('ascii')
        print(f'  ERR scrape_taj_cinemas: {err}')
        import traceback; traceback.print_exc()
        return None


async def scrape_prime_jo(cinema: dict) -> str | None:
    """
    Fetches showtimes from prime.jo with a simple HTTP GET —
    no JavaScript or AJAX needed, all data is server-rendered.
    """
    import aiohttp
    url = cinema['scraper_url']
    name = cinema['name_en']
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={
                    'User-Agent': random.choice(USER_AGENTS),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    print(f'  OK Got {len(html):,} chars from {name}')
                    return html
                else:
                    print(f'  ERR HTTP {resp.status} from {name}')
                    return None
    except Exception as e:
        err = str(e).encode('ascii', errors='replace').decode('ascii')
        print(f'  ERR Error loading {name}: {err}')
        return None


def parse_prime_jo_html(html: str, cinema: dict) -> list[dict]:
    """
    Custom regex parser for prime.jo cinema detail pages.
    Avoids sending large HTML to Claude (which causes JSON truncation).

    Page structure (linear, top-to-bottom):
      <a href="//www.prime.jo/Browsing/Movies/Details/...">Movie Title</a>
      ...
      <h4>Sunday, 17 May 2026</h4>    ← or similar heading with date
      ...
      <a href="//www.prime.jo/Ticketing/visSelectTickets.aspx?cinemacode=X&txtSessionId=Y...">
        <img src=".../AttributeIconGraphic/2D..." />
        07:00 PM
      </a>

    We collect (position, type, data) events in document order, then replay
    them to assign each showtime to its nearest preceding movie title + date.
    """
    import html as html_module
    from datetime import timedelta, datetime as dt_class

    today     = datetime.now(timezone.utc) + timedelta(hours=3)
    today_str = today.strftime('%Y-%m-%d')
    max_date  = (today + timedelta(days=7)).strftime('%Y-%m-%d')

    MONTHS = {m: i+1 for i, m in enumerate([
        'january','february','march','april','may','june',
        'july','august','september','october','november','december',
    ])}

    events: list[tuple[int, str, object]] = []   # (pos, type, data)

    # ── Movie title links ───────────────────────────────────────────────────────
    # The anchor may contain just text, or an <img> followed by text, or vice versa.
    # We strip inner HTML tags to get the text content.
    seen_titles_at: set[int] = set()
    for m in re.finditer(
        r'href=["\'](?:https?:)?//www\.prime\.jo/Browsing/Movies/Details/[^"\']+["\'][^>]*>([\s\S]{0,400}?)</a>',
        html, re.IGNORECASE,
    ):
        inner = m.group(1)
        # Strip HTML tags → plain text
        text = re.sub(r'<[^>]+>', ' ', inner)
        text = html_module.unescape(text).strip()
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) >= 2 and m.start() not in seen_titles_at:
            seen_titles_at.add(m.start())
            events.append((m.start(), 'movie', text))

    # ── Date headings: "Sunday, 17 May 2026" ───────────────────────────────────
    for m in re.finditer(
        r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
        r',\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August'
        r'|September|October|November|December)\s+(\d{4})',
        html, re.IGNORECASE,
    ):
        day   = int(m.group(1))
        month = MONTHS.get(m.group(2).lower(), 0)
        year  = int(m.group(3))
        if month:
            date_str = f'{year}-{month:02d}-{day:02d}'
            if today_str <= date_str <= max_date:
                events.append((m.start(), 'date', date_str))

    # ── Booking links (time + screen type embedded) ────────────────────────────
    cinema_code = (cinema.get('scraper_url') or '').rstrip('/').split('/')[-1]
    for m in re.finditer(
        r'href=["\'](?:https?:)?//www\.prime\.jo/Ticketing/visSelectTickets\.aspx\?'
        r'[^"\']*txtSessionId=(\d+)[^"\']*showtimeId=([^&"\']+)[^"\']*["\'][^>]*>'
        r'([\s\S]{0,400}?)</a>',
        html, re.IGNORECASE,
    ):
        session_id   = m.group(1)
        showtime_id  = m.group(2)
        inner        = m.group(3)

        # Time: "07:00 PM" or "11:00 AM"
        time_m = re.search(r'(\d{1,2}:\d{2})\s*(AM|PM)', inner, re.IGNORECASE)
        if not time_m:
            continue
        try:
            t = dt_class.strptime(f'{time_m.group(1)} {time_m.group(2).upper()}', '%I:%M %p')
            show_time = t.strftime('%H:%M')
        except ValueError:
            continue

        # Screen type from image src (e.g. "AttributeIconGraphic/2D")
        st_m = re.search(r'AttributeIconGraphic[/\\](\w[\w+]*)', inner, re.IGNORECASE)
        screen_type = (st_m.group(1) if st_m else '2D').upper().replace('+', 'X')
        if screen_type not in ('2D', '3D', 'IMAX', '4DX'):
            screen_type = '2D'

        booking_url = (
            f'https://www.prime.jo/Ticketing/visSelectTickets.aspx'
            f'?cinemacode={cinema_code}&txtSessionId={session_id}'
            f'&showtimeId={showtime_id}&visLang=1'
        )
        events.append((m.start(), 'showtime', {
            'show_time':    show_time,
            'screen_type':  screen_type,
            'booking_url':  booking_url,
        }))

    # ── Replay events in document order ───────────────────────────────────────
    events.sort(key=lambda x: x[0])
    showtimes: list[dict] = []
    current_movie: str | None = None
    current_date:  str | None = None

    for _pos, etype, data in events:
        if etype == 'movie':
            current_movie = data   # type: ignore[assignment]
            current_date  = None   # reset date context when movie changes
        elif etype == 'date':
            current_date = data    # type: ignore[assignment]
        elif etype == 'showtime' and current_movie and current_date:
            d = data               # type: ignore[assignment]
            showtimes.append({
                'movie_title_en': current_movie,
                'movie_title_ar': None,
                'show_date':      current_date,
                'show_time':      d['show_time'],
                'screen_type':    d['screen_type'],
                'language':       'English',
                'booking_url':    d['booking_url'],
            })

    return showtimes


async def scrape_cinema(cinema: dict) -> str | None:
    """
    Dispatches to the correct scraper based on the cinema's scraper_url.
    - prime.jo → simple HTTP GET (server-rendered HTML)
    - elcinema.com → Playwright + AJAX POST
    """
    import aiohttp
    from datetime import timedelta
    url = cinema['scraper_url']
    name = cinema['name_en']

    # Prime Cinemas has its own website with server-rendered showtimes
    if 'prime.jo' in url:
        return await scrape_prime_jo(cinema)

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
            # Only send elcinema.com cookies — sending all cookies causes nginx 400
            cookies = await context.cookies()
            ec_cookies = [c for c in cookies if 'elcinema' in c.get('domain', '')]
            cookie_header = '; '.join(f'{c["name"]}={c["value"]}' for c in ec_cookies)

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
                preview = (ajax_html or '')[:500].encode('ascii', errors='replace').decode('ascii')
                print(f'  WARN AJAX returned empty/small response ({len(ajax_html or "")} chars):')
                print(f'  {preview}')
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


async def _call_claude_for_chunk(
    chunk: str, cinema_name: str, today: str, chunk_num: int,
    date_mapping: dict[str, str] | None = None,
) -> list[dict]:
    """Calls Claude on one chunk of HTML and returns extracted showtimes."""

    date_hint = ''
    if date_mapping:
        mapping_lines = '\n'.join(f'  "{k}" → {v}' for k, v in date_mapping.items())
        date_hint = f"""
The HTML contains showtimes for multiple dates. Use this exact mapping to assign show_date:
{mapping_lines}
Match each showtime to its nearest preceding date section header (e.g. <h4> or <h2> with the Arabic date).
If you cannot determine the date for a showtime, use {today}.
"""
    else:
        date_hint = f"""
The HTML contains showtimes for multiple dates.
Dates may appear as English headings like "Sunday, 17 May 2026" — convert these to YYYY-MM-DD format.
Match each showtime to its nearest preceding date heading.
If you cannot determine the date for a showtime, use {today}.
"""

    prompt = f"""Extract movie showtimes from this HTML snippet for {cinema_name}.

This page is from elcinema.com — an Arabic cinema listings site.
Movie titles may appear in English, Arabic, or both.
Times appear as "9:15 مساء" (PM) or "10:00 صباحًا" (AM) — convert all to 24-hour HH:MM format.
  - صباحًا / ص = AM
  - مساءً / مساء / م = PM
{date_hint}
Return a JSON array where each object has exactly these keys:
- movie_title_en: string (English title — if only Arabic is present, transliterate it)
- movie_title_ar: string or null (Arabic title if present)
- show_date: string in YYYY-MM-DD format (use the date mapping above)
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

    # Extract the Arabic→YYYY-MM-DD date mapping from the date selector
    date_mapping = extract_date_mapping(html)
    if date_mapping:
        print(f'  >> Found date mapping: {date_mapping}')

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
            results = await _call_claude_for_chunk(chunk, cinema_name, today, i, date_mapping)
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

async def enrich_movie_with_claude(title_en: str, tmdb: dict | None = None) -> dict:
    """
    Enriches a movie with Arabic title, synopsis, genres, rating, and duration.
    Uses TMDB data where available; falls back to Claude for missing fields.
    """
    # Build what we already know from TMDB
    known = {
        'synopsis_en':   (tmdb or {}).get('synopsis_en'),
        'genre_tags':    (tmdb or {}).get('genre_tags') or [],
        'age_rating':    (tmdb or {}).get('age_rating') or 'NR',
        'duration_mins': (tmdb or {}).get('duration_mins'),
    }

    # Always ask Claude for: Arabic title + Arabic synopsis (TMDB doesn't have these)
    # Also fill in any fields TMDB missed
    missing = [f for f in ['synopsis_en', 'genre_tags', 'age_rating', 'duration_mins'] if not known[f]]
    fields_needed = ['title_ar', 'synopsis_ar'] + missing

    prompt = f"""For the movie "{title_en}", provide ONLY the following fields.
Return a JSON object with exactly these keys, no other text:
{chr(10).join(f'- {f}' for f in fields_needed)}

Field formats:
- title_ar: Arabic translation/transliteration of the title
- synopsis_ar: an 80-word Arabic synopsis
- synopsis_en: an 80-word English synopsis
- genre_tags: array of 2-4 genre strings e.g. ["Action", "Adventure"]
- age_rating: one of "G", "PG", "PG-13", "R", "NR"
- duration_mins: runtime as an integer, or null if unknown"""

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
        claude_data = json.loads(raw)
        print(f'  OK Enriched: {title_en} (TMDB+Claude)')
    except Exception as e:
        print(f'  WARN Claude enrichment failed for "{title_en}": {e}')
        claude_data = {}

    return {
        'title_ar':      claude_data.get('title_ar'),
        'synopsis_en':   known['synopsis_en'] or claude_data.get('synopsis_en'),
        'synopsis_ar':   claude_data.get('synopsis_ar'),
        'genre_tags':    known['genre_tags'] or claude_data.get('genre_tags', []),
        'age_rating':    known['age_rating'] if known['age_rating'] != 'NR' else claude_data.get('age_rating', 'NR'),
        'duration_mins': known['duration_mins'] or claude_data.get('duration_mins'),
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
    elcinema_data: dict[int, dict] | None = None,
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

    # Load all existing movies: indexed by slug, elcinema_id, title_ar, and tmdb_id
    movie_slug_to_id:      dict[str, str] = {}
    movie_ar_to_id:        dict[str, str] = {}
    movie_elcinema_to_id:  dict[int, str] = {}
    movie_tmdb_to_id:      dict[int, str] = {}
    existing_slugs:        set[str]       = set()
    elcinema_id_supported  = False
    try:
        res = supabase.table('movies').select('id, slug, title_ar, elcinema_id, tmdb_id, poster_url').execute()
        elcinema_id_supported = True
        for row in res.data:
            movie_slug_to_id[row['slug']] = row['id']
            existing_slugs.add(row['slug'])
            if row.get('title_ar'):
                movie_ar_to_id[row['title_ar'].strip().lower()] = row['id']
            if row.get('elcinema_id'):
                movie_elcinema_to_id[int(row['elcinema_id'])] = row['id']
            if row.get('tmdb_id'):
                movie_tmdb_to_id[int(row['tmdb_id'])] = row['id']
    except Exception:
        # Columns don't exist yet — fall back to slug + title_ar matching
        try:
            res = supabase.table('movies').select('id, slug, title_ar, poster_url').execute()
            for row in res.data:
                movie_slug_to_id[row['slug']] = row['id']
                existing_slugs.add(row['slug'])
                if row.get('title_ar'):
                    movie_ar_to_id[row['title_ar'].strip().lower()] = row['id']
        except Exception as e:
            print(f'  ERR Could not fetch existing movies: {e}')

    poster_map    = poster_map    or {}
    elcinema_data = elcinema_data or {}

    # Build reverse map: elcinema title → work_id
    elcinema_title_to_id: dict[str, int] = {
        v['title'].lower(): k for k, v in elcinema_data.items()
    }

    new_movies = 0
    for title_en, raw_st in seen_titles.items():
        slug = slugify(title_en)
        title_ar_raw = (raw_st.get('movie_title_ar') or '').strip()

        # Resolve elcinema work_id for this movie
        work_id = (
            elcinema_title_to_id.get(title_en.lower()) or
            (elcinema_title_to_id.get(title_ar_raw.lower()) if title_ar_raw else None)
        )

        # ── Fetch TMDB data early — needed for TMDB-ID dedup ─────────────────
        tmdb_data = await fetch_tmdb_data(title_en)
        tmdb_id   = (tmdb_data or {}).get('tmdb_id')
        poster_url = (tmdb_data or {}).get('poster_url')
        if poster_url:
            print(f'  >> TMDB data found for: {title_en}')

        # ── Check if movie already exists (priority order) ───────────────────
        # 1. elcinema work_id  — immune to all transliteration differences
        # 2. TMDB ID           — catches same film with different English titles
        # 3. Arabic title      — catches same film if elcinema/TMDB data present
        # 4. slug              — exact English title match
        existing_id   = None
        existing_slug = None

        if work_id and work_id in movie_elcinema_to_id:
            existing_id = movie_elcinema_to_id[work_id]
            existing_slug = next((s for s, i in movie_slug_to_id.items() if i == existing_id), None)
            if existing_slug and existing_slug != slug:
                print(f'  >> Matched "{title_en}" → existing movie via elcinema ID {work_id}')

        elif tmdb_id and tmdb_id in movie_tmdb_to_id and slug not in existing_slugs:
            existing_id = movie_tmdb_to_id[tmdb_id]
            existing_slug = next((s for s, i in movie_slug_to_id.items() if i == existing_id), None)
            if existing_slug:
                print(f'  >> Matched "{title_en}" → existing movie via TMDB ID {tmdb_id}')

        elif slug not in existing_slugs and title_ar_raw:
            ar_match_id = movie_ar_to_id.get(title_ar_raw.lower())
            if ar_match_id:
                existing_id = ar_match_id
                existing_slug = next((s for s, i in movie_slug_to_id.items() if i == ar_match_id), None)
                print(f'  >> Matched "{title_en}" → existing movie via Arabic title')

        if existing_id and existing_slug:
            movie_slug_to_id[slug] = existing_id
            slug = existing_slug

        if slug not in existing_slugs:
            # ── New movie: enrich and insert ─────────────────────────────────
            print(f'  >> Enriching new movie: {title_en}')
            enriched = await enrich_movie_with_claude(title_en, tmdb=tmdb_data)
            await asyncio.sleep(0.5)

            # ── Post-enrichment dedup: Arabic title re-check ─────────────────
            # Handles cases like "Bershamah" vs "BERSHAMA" — same Arabic title
            # after Claude enrichment even if English spellings differ.
            ar_enriched = (enriched.get('title_ar') or '').strip().lower()
            if ar_enriched and ar_enriched in movie_ar_to_id:
                dup_id   = movie_ar_to_id[ar_enriched]
                dup_slug = next((s for s, i in movie_slug_to_id.items() if i == dup_id), None)
                if dup_slug:
                    print(f'  >> Dedup: "{title_en}" → existing movie via Arabic title after enrichment')
                    movie_slug_to_id[slug] = dup_id
                    existing_slugs.add(slug)
                    slug = dup_slug
                    # Backfill TMDB data on existing record if missing
                    if poster_url or tmdb_id:
                        try:
                            upd: dict = {}
                            if poster_url:
                                upd['poster_url'] = poster_url
                            if tmdb_id:
                                upd['tmdb_id'] = tmdb_id
                            supabase.table('movies').update(upd).eq('id', dup_id)\
                                .is_('poster_url', 'null').execute()
                        except Exception:
                            pass
                    continue  # skip insertion — use existing movie for showtimes

            movie_row: dict = {
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
            if tmdb_id:
                movie_row['tmdb_id'] = tmdb_id
            try:
                res = supabase.table('movies').upsert(movie_row, on_conflict='slug').execute()
                new_id = res.data[0]['id']
                movie_slug_to_id[slug] = new_id
                existing_slugs.add(slug)
                # Update in-memory indexes so later movies in same run can dedup against this
                if tmdb_id:
                    movie_tmdb_to_id[tmdb_id] = new_id
                ar_title = movie_row.get('title_ar', '')
                if ar_title:
                    movie_ar_to_id[ar_title.strip().lower()] = new_id
                new_movies += 1
            except Exception as e:
                print(f'  ERR Failed to upsert movie "{title_en}": {e}')
        else:
            # ── Existing movie: backfill TMDB data if missing ─────────────────
            movie_id = movie_slug_to_id.get(slug)
            if movie_id and (poster_url or tmdb_id):
                try:
                    upd = {}
                    if poster_url:
                        upd['poster_url'] = poster_url
                    if tmdb_id:
                        upd['tmdb_id'] = tmdb_id
                    supabase.table('movies').update(upd).eq('id', movie_id)\
                        .is_('poster_url', 'null').execute()
                except Exception:
                    pass

    # Insert showtimes (ignore duplicates via UNIQUE constraint)
    from datetime import timedelta
    today_str   = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%Y-%m-%d')
    max_date_str = (datetime.now(timezone.utc) + timedelta(hours=3, days=7)).strftime('%Y-%m-%d')

    inserted = 0
    skipped_date = 0
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

        # Reject showtimes outside the valid window (today → today+7)
        if show_date < today_str or show_date > max_date_str:
            skipped_date += 1
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

    if skipped_date:
        print(f'  WARN Skipped {skipped_date} showtimes with out-of-range dates')
    print(f'  OK Saved {inserted} showtimes, {new_movies} new movies ({duration_ms}ms)')


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 (fallback): Deactivate persistently failing cinemas
# ─────────────────────────────────────────────────────────────────────────────

def handle_scrape_failure(cinema: dict, error_message: str, start_time: float) -> None:
    """Logs a failure for this cinema (never deactivates it automatically)."""
    duration_ms = int((time.time() - start_time) * 1000)
    supabase.table('scraper_logs').insert({
        'cinema_id':     cinema['id'],
        'status':        'failed',
        'error_message': error_message,
        'duration_ms':   duration_ms,
    }).execute()
    print(f'  WARN {cinema["name_en"]} failed — will retry next run')


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

async def run_scraper_for_cinema(cinema: dict) -> None:
    import traceback
    print(f'\n{"="*50}')
    print(f'Cinema: {cinema["name_en"]}')

    start = time.time()
    url = cinema.get('scraper_url', '')

    try:
        # ── Taj Cinemas: custom direct parser, no Claude ──────────────────────
        if 'tajcinemas.com' in url:
            showtimes = await scrape_taj_cinemas(cinema)
            if not showtimes:
                handle_scrape_failure(cinema, 'No showtimes found on tajcinemas.com', start)
                return
            await save_to_supabase(showtimes, cinema, start)
            return

        # ── Prime Cinemas: custom parser (HTML too large for Claude) ─────────
        if 'prime.jo' in url:
            html = await scrape_prime_jo(cinema)
            if not html:
                handle_scrape_failure(cinema, 'Failed to load prime.jo page', start)
                return
            if len(html) < 5_000:
                preview = html[:400].encode('ascii', errors='replace').decode('ascii')
                print(f'  WARN Small response from prime.jo ({len(html)} chars):')
                print(f'  {preview}')
                handle_scrape_failure(cinema, f'Small response from prime.jo ({len(html)} chars)', start)
                return
            showtimes = parse_prime_jo_html(html, cinema)
            print(f'  OK Parsed {len(showtimes)} showtimes from prime.jo (no Claude needed)')
            await save_to_supabase(showtimes, cinema, start)
            return

        # ── All other sources (elcinema): scrape HTML → Claude → save ────────
        html = await scrape_cinema(cinema)
        if not html:
            handle_scrape_failure(cinema, 'Failed to load page (timeout or bot block)', start)
            return

        if len(html) < 2_000:
            preview = html[:600].encode('ascii', errors='replace').decode('ascii')
            print(f'  WARN Small response ({len(html)} chars). Content:')
            print(f'  {preview}')
            handle_scrape_failure(cinema, f'Suspiciously small response ({len(html)} bytes)', start)
            return

        # Extract elcinema work IDs for deduplication (no poster URLs used)
        elcinema_data = extract_elcinema_data(html)
        poster_map: dict[str, str] = {}
        if elcinema_data:
            print(f'  >> Found {len(elcinema_data)} elcinema work ID(s) in HTML')

        showtimes = await parse_with_claude(html, cinema['name_en'])
        await save_to_supabase(showtimes, cinema, start, poster_map, elcinema_data)

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
