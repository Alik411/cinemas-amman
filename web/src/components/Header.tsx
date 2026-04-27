'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Film, Search, Menu, X } from 'lucide-react'
import { useState } from 'react'

interface HeaderProps {
  locale: string
}

export default function Header({ locale }: HeaderProps) {
  const t = useTranslations()
  const [menuOpen, setMenuOpen] = useState(false)

  async function switchLocale() {
    const newLocale = locale === 'en' ? 'ar' : 'en'
    document.cookie = `locale=${newLocale}; path=/; max-age=31536000`
    window.location.reload()
  }

  return (
    <header className="sticky top-0 z-50 bg-zinc-950/95 backdrop-blur border-b border-zinc-800">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 font-bold text-amber-400 text-lg">
          <Film size={22} />
          <span>{locale === 'ar' ? 'سينما عمّان' : 'CineAmman'}</span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-6 text-sm text-zinc-300">
          <Link href="/" className="hover:text-white transition-colors">{t('nav.home')}</Link>
          <Link href="/search" className="hover:text-white transition-colors">{t('nav.movies')}</Link>
          <Link href="/search" className="hover:text-white transition-colors">{t('nav.cinemas')}</Link>
        </nav>

        <div className="flex items-center gap-3">
          <Link href="/search" className="text-zinc-400 hover:text-white transition-colors">
            <Search size={18} />
          </Link>
          <button
            onClick={switchLocale}
            className="text-xs font-medium px-3 py-1.5 rounded-full border border-zinc-700 text-zinc-300 hover:border-amber-400 hover:text-amber-400 transition-colors"
          >
            {t('common.language')}
          </button>
          <button
            className="md:hidden text-zinc-400 hover:text-white"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="md:hidden border-t border-zinc-800 bg-zinc-950 px-4 py-3 flex flex-col gap-3 text-sm text-zinc-300">
          <Link href="/" onClick={() => setMenuOpen(false)} className="hover:text-white">{t('nav.home')}</Link>
          <Link href="/search" onClick={() => setMenuOpen(false)} className="hover:text-white">{t('nav.movies')}</Link>
          <Link href="/search" onClick={() => setMenuOpen(false)} className="hover:text-white">{t('nav.cinemas')}</Link>
        </div>
      )}
    </header>
  )
}
