import type { CSSProperties } from 'react'

const hue = (s: string) => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 11)
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
    <span className={`avatar ${size ?? ''}`} style={{ '--h': hue(name) } as CSSProperties} aria-hidden="true">
      {initials(name)}
    </span>
  )
}
