import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import { toJordanDate } from '@/lib/utils'

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const date = searchParams.get('date') ?? toJordanDate()
  const cinemaId = searchParams.get('cinema_id')

  const supabase = await createClient()
  let query = supabase
    .from('showtimes')
    .select('*, movies(*), cinemas(*)')
    .eq('show_date', date)
    .order('show_time')

  if (cinemaId) query = query.eq('cinema_id', cinemaId)

  const { data, error } = await query
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ data })
}
