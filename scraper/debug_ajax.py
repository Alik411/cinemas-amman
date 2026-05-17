"""
Quick debug script — fetches the raw AJAX HTML from elcinema for one cinema
and saves it so we can inspect the date/showtime structure.
"""
import asyncio
import os
import random
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from playwright.async_api import async_playwright
import aiohttp

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'), encoding='utf-8-sig', override=True)

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
]

# Change this to whichever cinema URL you want to debug
TEST_URL = 'https://elcinema.com/en/theater/3101465/'  # Grand Cinemas Abdali Mall


async def main():
    today = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%Y-%m-%d')
    print(f'Fetching AJAX for date: {today}')
    print(f'URL: {TEST_URL}')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale='en-US',
        )
        page = await context.new_page()
        await page.goto(TEST_URL, timeout=60_000, wait_until='load')
        await asyncio.sleep(2)

        csrf_token = await page.locator('meta[name="csrf-token"]').get_attribute('content')
        theater_id = await page.locator('#theater-showtimes-date-selector').get_attribute('data-id')
        cookies = await context.cookies()
        # Only send elcinema.com cookies — sending all cookies causes nginx 400
        ec_cookies = [c for c in cookies if 'elcinema' in c.get('domain', '')]
        cookie_header = '; '.join(f'{c["name"]}={c["value"]}' for c in ec_cookies)
        print(f'Cookies (elcinema only): {len(ec_cookies)} of {len(cookies)} total')

        print(f'Theater ID: {theater_id}')
        print(f'CSRF token: {csrf_token[:20]}...')

        await browser.close()

    async with aiohttp.ClientSession() as session:
        async with session.post(
            'https://elcinema.com/theater/ajax_show',
            data={'date': today, 'id': theater_id},
            headers={
                'X-CSRF-Token': csrf_token,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': TEST_URL,
                'Origin': 'https://elcinema.com',
                'Cookie': cookie_header,
                'User-Agent': random.choice(USER_AGENTS),
                'X-Requested-With': 'XMLHttpRequest',
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            html = await resp.text()
            print(f'\nAJAX response: {len(html):,} chars, status {resp.status}')

    # Save full response
    with open('ajax_response.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('Saved full response to ajax_response.html')

    # Print first 5000 chars so we can see the structure
    print('\n--- FIRST 5000 CHARS ---')
    print(html[:5000])
    print('\n--- LAST 2000 CHARS ---')
    print(html[-2000:])

asyncio.run(main())
