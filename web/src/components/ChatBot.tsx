'use client'

import { useState, useRef, useEffect } from 'react'
import { useTranslations } from 'next-intl'
import { MessageCircle, X, Send } from 'lucide-react'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface ChatBotProps {
  locale: string
}

export default function ChatBot({ locale }: ChatBotProps) {
  const t = useTranslations('chatbot')
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: t('welcome') }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  async function sendMessage() {
    const text = input.trim()
    if (!text || loading) return

    const newMessages: Message[] = [...messages, { role: 'user', content: text }]
    setMessages(newMessages)
    setInput('')
    setLoading(true)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: newMessages.slice(-10), locale }),
      })

      if (!res.ok) throw new Error('API error')
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: locale === 'ar'
          ? 'عذراً، حدث خطأ. يرجى المحاولة مرة أخرى.'
          : 'Sorry, something went wrong. Please try again.',
      }])
    } finally {
      setLoading(false)
    }
  }

  const isRtl = locale === 'ar'

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setOpen(true)}
        className={`fixed bottom-6 ${isRtl ? 'left-6' : 'right-6'} z-50 bg-amber-500 hover:bg-amber-400 text-black rounded-full p-4 shadow-lg shadow-amber-500/30 transition-all hover:scale-110 ${open ? 'hidden' : 'flex'}`}
        aria-label={t('open')}
      >
        <MessageCircle size={24} />
      </button>

      {/* Chat drawer */}
      {open && (
        <div className={`fixed bottom-0 ${isRtl ? 'left-0' : 'right-0'} z-50 w-full sm:w-96 h-[520px] bg-zinc-900 border border-zinc-700 sm:rounded-t-2xl flex flex-col shadow-2xl`}>
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-zinc-800">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-amber-500 flex items-center justify-center">
                <MessageCircle size={16} className="text-black" />
              </div>
              <span className="font-semibold text-white text-sm">{t('title')}</span>
            </div>
            <button onClick={() => setOpen(false)} className="text-zinc-400 hover:text-white transition-colors">
              <X size={20} />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === 'user' ? (isRtl ? 'justify-start' : 'justify-end') : (isRtl ? 'justify-end' : 'justify-start')}`}>
                <div className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-amber-500 text-black font-medium'
                    : 'bg-zinc-800 text-zinc-100'
                }`}>
                  {msg.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className={`flex ${isRtl ? 'justify-end' : 'justify-start'}`}>
                <div className="bg-zinc-800 rounded-2xl px-4 py-2 text-sm text-zinc-400">
                  {t('typing')}
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="p-3 border-t border-zinc-800 flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage()}
              placeholder={t('placeholder')}
              className="flex-1 bg-zinc-800 text-white text-sm rounded-xl px-4 py-2.5 outline-none placeholder:text-zinc-500 focus:ring-1 focus:ring-amber-500"
              dir={isRtl ? 'rtl' : 'ltr'}
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || loading}
              className="bg-amber-500 hover:bg-amber-400 disabled:opacity-40 text-black rounded-xl px-3 transition-colors"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      )}
    </>
  )
}
