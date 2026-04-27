"""
Test a single cinema by slug.
Usage: python test_single.py grand-cinemas-city-mall
"""

import asyncio
import sys
import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

from main import run_scraper_for_cinema

SUPABASE_URL = os.environ['NEXT_PUBLIC_SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


async def test(slug: str) -> None:
    result = supabase.table('cinemas').select('*').eq('slug', slug).execute()
    if not result.data:
        print(f'Error: no cinema found with slug "{slug}"')
        print('\nAvailable slugs:')
        all_cinemas = supabase.table('cinemas').select('slug, name_en').execute()
        for c in all_cinemas.data:
            print(f'  {c["slug"]}  ({c["name_en"]})')
        return

    cinema = result.data[0]
    # Temporarily mark active so the scraper doesn't skip it
    cinema['active'] = True
    await run_scraper_for_cinema(cinema)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python test_single.py <cinema-slug>')
        print('Example: python test_single.py grand-cinemas-city-mall')
        sys.exit(1)

    asyncio.run(test(sys.argv[1]))
