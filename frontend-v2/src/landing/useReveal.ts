import { useEffect } from 'react'

/**
 * Sections rise into place once, the first time they scroll into view. Small (12px) and quick, so it
 * reads as content settling rather than a show. With reduced motion, CSS keeps everything still.
 */
export function useReveal(root: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const els = root.current?.querySelectorAll<HTMLElement>('[data-reveal]')
    if (!els?.length) return
    if (!('IntersectionObserver' in window)) {
      els.forEach((el) => el.classList.add('in'))
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue
          e.target.classList.add('in')
          io.unobserve(e.target)
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.12 },
    )
    els.forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [root])
}
