import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { NextIntlClientProvider } from 'next-intl'
import { getLocale, getMessages } from 'next-intl/server'
import { Analytics } from '@vercel/analytics/next'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'CineAmman | سينما عمّان',
  description: 'All Amman cinema showtimes in one place — جميع عروض سينمات عمّان في مكان واحد',
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
