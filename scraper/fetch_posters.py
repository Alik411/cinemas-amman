"""
Fetch movie posters and metadata from TMDB for all movies missing a poster.
Usage: python fetch_posters.py
"""

import asyncio
import os
import re
import httpx
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'), encoding='utf-8-sig')

TMDB_TOKEN   = os.environ['TMDB_API_KEY']
SUPABASE_URL = os.environ['NEXT_PUBLIC_SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TMDB_BASE      = 'https://api.themoviedb.org/3'
TMDB_IMG_BASE  = 'https://image.tmdb.org/t/p/w500'
HEADERS        = {'Authorization': f'Bearer {TMDB_TOKEN}', 'accept': 'application/json'}


def clean_title(title: str) -> str:
    """Remove common noise from scraped titles before searching."""
    title = re.sub(r'\s*\(.*?\)', '', title)   # remove parentheses
    title = re.sub(r'\s*\[.*?\]', '', title)   # remove brackets
    return title.strip()


async def search_tmdb(client: httpx.AsyncClient, title: str) -> dict | None:
    """Search TMDB for a movie title, return best match or None."""
    query = clean_title(title)
    try:
        resp = await client.get(
            f'{TMDB_BASE}/search/movie',
            params={'query': query, 'language': 'en-US', 'page': 1},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get('results', [])
        if not results:
            return None
        # Return the most popular result
        return max(results, key=lambda x: x.get('popularity', 0))
    except Exception as e:
        print(f'  ✗ TMDB search failed for "{title}": {e}')
        return None


async def get_trailer(client: httpx.AsyncClient, tmdb_id: int) -> str | None:
    """Fetch YouTube trailer ID for a TMDB movie."""
    try:
        resp = await client.get(
            f'{TMDB_BASE}/movie/{tmdb_id}/videos',
            params={'language': 'en-US'},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        videos = resp.json().get('results', [])
        trailers = [v for v in videos if v.get('site') == 'YouTube' and v.get('type') == 'Trailer']
        return trailers[0]['key'] if trailers else None
    except Exception:
        return None


async def fetch_all_posters() -> None:
    print('=' * 50)
    print('CineAmman — Fetching TMDB posters')
    print('=' * 50)

    # Get all movies that are missing a poster
    result = supabase.table('movies').select('id, title_en, slug, poster_url, tmdb_id').execute()
    movies = result.data or []
    missing = [m for m in movies if not m.get('poster_url')]

    if not missing:
        print('All movies already have posters!')
        return

    print(f'Found {len(missing)} movies without posters\n')

    async with httpx.AsyncClient() as client:
        for movie in missing:
            title = movie['title_en']
            print(f'  Searching: {title}')

            tmdb = await search_tmdb(client, title)
            if not tmdb:
                print(f'  ✗ Not found on TMDB')
                continue

            poster_path = tmdb.get('poster_path')
            tmdb_id     = tmdb.get('id')
            poster_url  = f'{TMDB_IMG_BASE}{poster_path}' if poster_path else None
            trailer_id  = await get_trailer(client, tmdb_id) if tmdb_id else None

            update = {}
            if poster_url:
                update['poster_url'] = poster_url
            if tmdb_id:
                update['tmdb_id'] = tmdb_id
            if trailer_id:
                update['trailer_youtube_id'] = trailer_id

            if update:
                supabase.table('movies').update(update).eq('id', movie['id']).execute()
                print(f'  ✓ {title} → poster: {"yes" if poster_url else "no"}, trailer: {"yes" if trailer_id else "no"}')
            else:
                print(f'  ✗ {title} → no poster or trailer found')

            await asyncio.sleep(0.25)   # stay well within TMDB rate limits

    print('\nDone!')


if __name__ == '__main__':
    asyncio.run(fetch_all_posters())
