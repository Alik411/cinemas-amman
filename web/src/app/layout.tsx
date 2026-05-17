import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { NextIntlClientProvider } from 'next-intl'
import { getLocale, getMessages } from 'next-intl/server'
import { Analytics } from '@vercel/analytics/next'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  metadataBase: new URL('https://www.cineamman.com'),
  title: {
    default: 'CineAmman | سينما عمّان — أوقات عروض سينمات عمّان',
    template: '%s | CineAmman سينما عمّان',
  },
  description:
    'أوقات عروض جميع سينمات عمّان في مكان واحد — Grand Cinemas, Prime Cinemas, Taj Cinemas. ' +
    'All Amman cinema showtimes: movies, times & booking links.',
  keywords: [
    'سينما عمان', 'سينمات عمان', 'افلام عمان', 'عروض سينما عمان',
    'cinema amman', 'cinemas amman', 'movies amman', 'amman showtimes',
    'grand cinemas amman', 'prime cinemas jordan', 'taj cinemas amman',
    'what\'s on amman', 'أفلام اليوم عمان',
  ],
  alternates: {
    canonical: 'https://www.cineamman.com',
    languages: {
      'en': 'https://www.cineamman.com',
      'ar': 'https://www.cineamman.com',
      'x-default': 'https://www.cineamman.com',
    },
  },
  openGraph: {
    type: 'website',
    url: 'https://www.cineamman.com',
    siteName: 'CineAmman | سينما عمّان',
    title: 'CineAmman | سينما عمّان — أوقات عروض سينمات عمّان',
    description:
      'جميع أوقات عروض سينمات عمّان في مكان واحد — All Amman cinema showtimes in one place.',
    locale: 'ar_JO',
    alternateLocale: 'en_US',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'CineAmman | سينما عمّان',
    description: 'جميع أوقات عروض سينمات عمّان في مكان واحد',
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true },
  },
  verification: {
    google: '85qoVplLBCw-OHBeObgGXnRdF63AuoCd3W9yineRmzg',
  },
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale()
  const messages = await getMessages()
  const isArabic = locale === 'ar'

  return (
    <html lang={locale} dir={isArabic ? 'rtl' : 'ltr'}>
      <head>
        {isArabic && (
          <link
            href="https://fonts.googleapis.com/css2?family=Noto+Naskh+Arabic:wght@400;500;600;700&display=swap"
            rel="stylesheet"
            media="all"
          />
        )}
      </head>
      <body
        className={inter.className}
        style={isArabic ? { fontFamily: "'Noto Naskh Arabic', sans-serif" } : {}}
      >
        <NextIntlClientProvider messages={messages} locale={locale}>
          {children}
        </NextIntlClientProvider>
        <Analytics />
      </body>
    </html>
  )
}
