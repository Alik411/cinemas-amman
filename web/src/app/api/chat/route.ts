import { NextRequest, NextResponse } from 'next/server'
import Anthropic from '@anthropic-ai/sdk'
import { createServiceClient } from '@/lib/supabase/server'
import { toJordanDate, getTomorrowJordan } from '@/lib/utils'

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY! })

export async function POST(req: NextRequest) {
  try {
    const { message, history, locale } = await req.json()
    if (!message) return NextResponse.json({ error: 'No message' }, { status: 400 })

    const supabase = createServiceClient()
    const today = toJordanDate()
    const tomorrow = getTomorrowJordan()

    const { data: showtimes } = await supabase
      .from('showtimes')
      .select('show_date, show_time, screen_type, language, booking_url, movies(title_en, title_ar, genre_tags, duration_mins), cinemas(name_en, name_ar)')
      .gte('show_date', today)
      .lte('show_date', tomorrow)
      .limit(200)

    const showtimesJson = JSON.stringify(showtimes ?? [])

    const systemPrompt = `You are CineAmman's friendly cinema guide for Amman, Jordan. You help people find movies and showtimes. You have access to today's and tomorrow's complete showtimes for all Amman cinemas.

Current showtimes data:
${showtimesJson.slice(0, 8000)}

Rules:
- Always be helpful and friendly
- If asked in Arabic, respond in Arabic. If asked in English, respond in English.
- When recommending movies, mention the specific cinema and showtime
- If someone asks about a movie not in the showtimes, say it may not be showing yet
- Keep responses concise and conversational (2-4 sentences max)
- Use cinema and movie names in both languages when relevant
- Today is ${today}`

    const messages = [
      ...(history ?? []).slice(-8).map((m: any) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      })),
      { role: 'user' as const, content: message },
    ]

    const response = await anthropic.messages.create({
      model: 'claude-sonnet-4-5',
      max_tokens: 512,
      system: systemPrompt,
      messages,
    })

    const reply = response.content[0].type === 'text' ? response.content[0].text : ''
    return NextResponse.json({ reply })

  } catch (error) {
    console.error('Chat API error:', error)
    return NextResponse.json({
      reply: 'Sorry, I ran into an issue. Please try again! / عذراً، حدث خطأ. يرجى المحاولة مرة أخرى.',
    })
  }
}
