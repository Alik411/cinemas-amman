import { format, parseISO } from 'date-fns'

export function formatTime12h(time: string): string {
  const [hours, minutes] = time.split(':').map(Number)
  const period = hours >= 12 ? 'PM' : 'AM'
  const h = hours % 12 || 12
  return `${h}:${minutes.toString().padStart(2, '0')} ${period}`
}

export function formatDate(dateStr: string, locale: string = 'en'): string {
  const date = parseISO(dateStr)
  if (locale === 'ar') {
    return format(date, 'EEEE, d MMMM yyyy')
  }
  return format(date, 'EEEE, MMMM d, yyyy')
}

export function toJordanDate(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Amman' })
}

export function getTomorrowJordan(): string {
  const d = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Amman' }))
  d.setDate(d.getDate() + 1)
  return d.toISOString().split('T')[0]
}

export function cn(...classes: (string | undefined | false | null)[]): string {
  return classes.filter(Boolean).join(' ')
}
