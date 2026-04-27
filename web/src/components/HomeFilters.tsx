'use client'

import { useTranslations } from 'next-intl'
import type { Cinema } from '@/types/database'

interface HomeFiltersProps {
  cinemas: Cinema[]
  locale: string
}

export default function HomeFilters({ cinemas, locale }: HomeFiltersProps) {
  const t = useTranslations('home')

  return (
    <div className="flex flex-wrap gap-3">
      <select className="bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500">
        <option value="">{t('filterByCinema')}</option>
        {cinemas.map(c => (
          <option key={c.id} value={c.slug}>
            {locale === 'ar' ? c.name_ar : c.name_en}
          </option>
        ))}
      </select>

      <select className="bg-zinc-800 border border-zinc-700 text-zinc-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-amber-500">
        <option value="">{t('filterByType')}</option>
        <option value="2D">2D</option>
        <option value="3D">3D</option>
        <option value="IMAX">IMAX</option>
        <option value="4DX">4DX</option>
      </select>
    </div>
  )
}
