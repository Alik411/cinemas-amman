"""
deduplicate.py  —  one-time cleanup of duplicate movie records.

Finds movies that are the same film but were inserted with slightly different
titles (different transliterations, "The" prefix, "3D" suffix, etc.) and
merges them, keeping the record with the most showtimes.

Usage:
  python deduplicate.py          # dry run — shows what would be merged
  python deduplicate.py --apply  # actually performs the merges
"""

import asyncio
import os
import re
import sys
from dotenv import load_dotenv
from supabase import create_client, Client
import aiohttp

load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'),
    encoding='utf-8-sig', override=True,
)

SUPABASE_URL = os.environ['NEXT_PUBLIC_SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']
TMDB_API_KEY = os.environ.get('TMDB_API_KEY', '')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
APPLY = '--apply' in sys.argv


# ─────────────────────────────────────────────────────────────────────────────
# Title normalisation (mirrors main.py — keep in sync)
# ─────────────────────────────────────────────────────────────────────────────

def normalize_for_dedup(title: str) -> str:
    """
    Aggressive normalisation used only for grouping potential duplicates.
    Strips articles, format suffixes, parentheticals, punctuation.
    NOT used for display — only for comparison.
    """
    t = title.strip()

    # Strip trailing screen-format suffixes
    t = re.sub(r'\s+(?:3D|IMAX|4DX|Taj\s+Class)\s*$', '', t, flags=re.IGNORECASE)

    # Strip concert-film descriptors like " - The Tour (Live in 3D)"
    t = re.sub(r'\s+-\s+(?:The\s+)?(?:Tour|Live)[^)]*\(.*?\)\s*$', '', t, flags=re.IGNORECASE)

    # Prefer shorter parenthetical title e.g. "El Kalam Ala Eh (Awel Leila)" → "Awel Leila"
    paren = re.match(r'^(.+?)\s*\(([^)]{3,})\)\s*$', t)
    if paren:
        before, inside = paren.group(1).strip(), paren.group(2).strip()
        if len(inside) < len(before) * 0.8:
            t = inside

    # Strip leading articles
    t = re.sub(r'^(?:The|A|An)\s+', '', t, flags=re.IGNORECASE)

    # Lowercase and strip all non-alphanumeric for bare comparison
    t = t.lower()
    t = re.sub(r'[^a-z0-9]', '', t)
    return t


# ─────────────────────────────────────────────────────────────────────────────
# TMDB lookup
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_tmdb_id(session: aiohttp.ClientSession, title: str) -> int | None:
    if not TMDB_API_KEY:
        return None
    try:
        async with session.get(
            'https://api.themoviedb.org/3/search/movie',
            params={'query': title, 'language': 'en-US', 'page': 1},
            headers={'Authorization': f'Bearer {TMDB_API_KEY}', 'accept': 'application/json'},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = data.get('results', [])
                if results:
                    return int(results[0]['id'])
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    if not APPLY:
        print('DRY RUN — pass --apply to actually merge records\n')

    # ── Load all movies ───────────────────────────────────────────────────────
    movies = supabase.table('movies').select(
        'id, title_en, title_ar, slug, tmdb_id, poster_url, synopsis_en'
    ).execute().data

    # Load showtime counts per movie
    showtimes = supabase.table('showtimes').select('movie_id').execute().data
    counts: dict[str, int] = {}
    for row in showtimes:
        mid = row['movie_id']
        counts[mid] = counts.get(mid, 0) + 1
    for m in movies:
        m['showtime_count'] = counts.get(m['id'], 0)

    print(f'Loaded {len(movies)} movies, {len(showtimes)} showtimes\n')

    # ── Step 1: Backfill missing TMDB IDs ────────────────────────────────────
    print('── Backfilling missing TMDB IDs ─────────────────────────────────────')
    missing_tmdb = [m for m in movies if not m.get('tmdb_id')]
    print(f'  {len(missing_tmdb)} movie(s) without TMDB ID')

    async with aiohttp.ClientSession() as http:
        for m in missing_tmdb:
            # Try original title first, then normalised form
            tmdb_id = await fetch_tmdb_id(http, m['title_en'])
            if not tmdb_id:
                norm = normalize_for_dedup(m['title_en'])
                tmdb_id = await fetch_tmdb_id(http, norm)
            if tmdb_id:
                print(f"  {m['title_en']} → TMDB {tmdb_id}")
                m['tmdb_id'] = tmdb_id
                if APPLY:
                    try:
                        supabase.table('movies').update({'tmdb_id': tmdb_id})\
                            .eq('id', m['id']).execute()
                    except Exception as e:
                        print(f"    WARN could not save tmdb_id: {e}")
            await asyncio.sleep(0.25)

    # ── Step 2: Group duplicates ──────────────────────────────────────────────
    print('\n── Detecting duplicate groups ───────────────────────────────────────')

    assigned: set[str] = set()
    groups: list[list[dict]] = []

    # 2a. Group by TMDB ID (most reliable)
    tmdb_buckets: dict[int, list[dict]] = {}
    for m in movies:
        if m.get('tmdb_id'):
            tmdb_buckets.setdefault(int(m['tmdb_id']), []).append(m)

    for tid, group in tmdb_buckets.items():
        if len(group) > 1:
            groups.append(group)
            for m in group:
                assigned.add(m['id'])

    # 2b. Group remaining movies by normalised title key
    norm_buckets: dict[str, list[dict]] = {}
    for m in movies:
        if m['id'] in assigned:
            continue
        key = normalize_for_dedup(m['title_en'])
        if key:
            norm_buckets.setdefault(key, []).append(m)

    for key, group in norm_buckets.items():
        if len(group) > 1:
            groups.append(group)
            for m in group:
                assigned.add(m['id'])

    if not groups:
        print('  No duplicates found — nothing to do.')
        return

    print(f'  Found {len(groups)} duplicate group(s), '
          f'{sum(len(g) - 1 for g in groups)} record(s) to remove\n')

    # ── Step 3: Merge each group ──────────────────────────────────────────────
    total_removed = 0

    for group in groups:
        # Pick the canonical record: most showtimes → most complete data
        group.sort(key=lambda m: (
            m['showtime_count'],
            bool(m.get('poster_url')),
            bool(m.get('synopsis_en')),
            bool(m.get('title_ar')),
        ), reverse=True)

        canonical  = group[0]
        duplicates = group[1:]

        print(f'  KEEP   "{canonical["title_en"]}"  '
              f'(slug={canonical["slug"]}, showtimes={canonical["showtime_count"]})')
        for dup in duplicates:
            print(f'  REMOVE "{dup["title_en"]}"  '
                  f'(slug={dup["slug"]}, showtimes={dup["showtime_count"]})')

        if APPLY:
            for dup in duplicates:
                # Move showtimes from duplicate → canonical
                moved = supabase.table('showtimes').update({'movie_id': canonical['id']})\
                    .eq('movie_id', dup['id']).execute()

                # Backfill any fields that canonical is missing
                upd: dict = {}
                for field in ('poster_url', 'title_ar', 'synopsis_en', 'synopsis_ar',
                               'tmdb_id', 'genre_tags', 'duration_mins', 'age_rating'):
                    if not canonical.get(field) and dup.get(field):
                        upd[field] = dup[field]
                        canonical[field] = dup[field]  # keep in-memory consistent
                if upd:
                    supabase.table('movies').update(upd).eq('id', canonical['id']).execute()

                # Delete the duplicate movie row
                supabase.table('movies').delete().eq('id', dup['id']).execute()
                total_removed += 1
                print(f'    ✓ Merged + deleted "{dup["title_en"]}"')

        print()

    if APPLY:
        print(f'Done — removed {total_removed} duplicate record(s).')
    else:
        total = sum(len(g) - 1 for g in groups)
        print(f'DRY RUN — run with --apply to remove {total} duplicate(s).')


if __name__ == '__main__':
    asyncio.run(main())
