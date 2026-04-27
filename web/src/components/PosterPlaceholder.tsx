interface PosterPlaceholderProps {
  title: string
  className?: string
}

const gradients = [
  'from-purple-900 to-indigo-900',
  'from-rose-900 to-orange-900',
  'from-teal-900 to-cyan-900',
  'from-amber-900 to-yellow-900',
  'from-pink-900 to-purple-900',
]

export default function PosterPlaceholder({ title, className = '' }: PosterPlaceholderProps) {
  const index = title.charCodeAt(0) % gradients.length
  return (
    <div className={`bg-gradient-to-br ${gradients[index]} flex items-end p-3 ${className}`}>
      <span className="text-white font-semibold text-sm leading-tight line-clamp-3">{title}</span>
    </div>
  )
}
