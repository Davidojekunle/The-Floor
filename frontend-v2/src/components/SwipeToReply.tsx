import { useEffect, useRef, type ReactNode } from 'react'
import { rubberband, spring, type SpringHandle } from '../lib/spring'
import { Icon } from './Icon'

const SLOP = 10 // px before deciding: swipe (sideways) or scroll (up/down)
const THRESHOLD = 64 // px: let go past this and it's a reply

/**
 * Swipe a chat row to the right to reply (touch only; desktop has the Reply button).
 * The row tracks the finger 1:1, resists past the threshold, ticks once (haptic) when it gets there,
 * and springs home from wherever it is at the release velocity. Vertical moves are left to scrolling.
 */
export function SwipeToReply({ onReply, enabled, id, children }: { onReply: () => void; enabled: boolean; id: string; children: ReactNode }) {
  const wrap = useRef<HTMLDivElement>(null)
  const row = useRef<HTMLDivElement>(null)
  const replyRef = useRef(onReply)
  useEffect(() => {
    replyRef.current = onReply
  })

  useEffect(() => {
    const el = row.current
    const outer = wrap.current
    if (!el || !outer || !enabled) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let mode: 'idle' | 'pending' | 'drag' = 'idle'
    let pointer = -1
    let startX = 0
    let startY = 0
    let x = 0
    let armed = false
    let samples: { t: number; x: number }[] = []
    let anim: SpringHandle | null = null

    const set = (v: number) => {
      x = v
      el.style.transform = v ? `translate3d(${v}px, 0, 0)` : ''
      outer.style.setProperty('--swipe', String(Math.min(1, v / THRESHOLD)))
    }

    const down = (e: PointerEvent) => {
      if (e.pointerType !== 'touch' || mode !== 'idle') return
      anim?.stop() // grab it mid-spring: carry on from where it is
      pointer = e.pointerId
      startX = e.clientX - x
      startY = e.clientY
      samples = []
      mode = 'pending'
    }

    const move = (e: PointerEvent) => {
      if (e.pointerId !== pointer || mode === 'idle') return
      const dx = e.clientX - startX
      if (mode === 'pending') {
        const dy = e.clientY - startY
        if (Math.abs(dx - x) < SLOP && Math.abs(dy) < SLOP) return
        if (Math.abs(dy) > Math.abs(dx - x) || dx - x < 0) {
          mode = 'idle' // a scroll, or a swipe the wrong way: not ours
          return
        }
        mode = 'drag'
        el.setPointerCapture(pointer)
      }
      const v = dx <= 0 ? 0 : dx <= THRESHOLD ? dx : THRESHOLD + rubberband(dx - THRESHOLD, 160)
      set(v)
      const now = performance.now()
      samples.push({ t: now, x: v })
      samples = samples.filter((s) => now - s.t < 100)
      const past = v >= THRESHOLD
      if (past !== armed) {
        armed = past
        if (past) navigator.vibrate?.(8) // one tick when it would count
      }
    }

    const up = (e: PointerEvent) => {
      if (e.pointerId !== pointer) return
      const dragging = mode === 'drag'
      mode = 'idle'
      pointer = -1
      if (!dragging) return
      if (armed) replyRef.current()
      armed = false
      const first = samples[0]
      const last = samples[samples.length - 1]
      const velocity = first && last && last.t > first.t ? ((last.x - first.x) / (last.t - first.t)) * 1000 : 0
      if (reduce) return set(0)
      anim = spring(x, 0, set, { dampingRatio: 1, response: 0.3, velocity })
    }

    el.addEventListener('pointerdown', down)
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
    el.addEventListener('pointercancel', up)
    return () => {
      anim?.stop()
      el.removeEventListener('pointerdown', down)
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerup', up)
      el.removeEventListener('pointercancel', up)
      set(0)
    }
  }, [enabled])

  return (
    <div className="swipe" ref={wrap} data-mid={id}>
      {enabled && (
        <span className="swipe-ico" aria-hidden="true">
          <Icon name="reply" size={18} />
        </span>
      )}
      <div className="swipe-row" ref={row}>
        {children}
      </div>
    </div>
  )
}
