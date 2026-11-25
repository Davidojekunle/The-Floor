import type { CSSProperties } from 'react'

// FNV-1a over the whole name: similar names (two "DO"s) land on clearly different colours
const hue = (s: string) => {
  let h = 2166136261
  for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619)
  return ((h >>> 0) % 12) * 30 + 15 // 12 well-separated hues
}
const initials = (n: string) =>
  n
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

export function Avatar({ name, size }: { name: string; size?: 'sm' }) {
  return (
    <span className={`avatar ${size ?? ''}`} style={{ '--h': hue(name) } as CSSProperties} aria-hidden="true" title={name}>
      {initials(name)}
    </span>
  )
}
