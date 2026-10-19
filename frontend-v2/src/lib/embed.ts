/**
 * What a result link can show inline. Players load only when someone taps them, so a task page with
 * five results doesn't pull five video players (or tell five services who's looking) on open.
 */
export type Embed =
  | { kind: 'frame'; src: string; provider: string; shape: Shape; thumb?: string; verb: 'Play' | 'Preview' }
  | { kind: 'image'; src: string; provider: string }
  | { kind: 'video'; src: string; provider: string }
  | { kind: 'link'; provider: string }

type Shape = 'wide' | 'tall' | 'page' // 16:9 video, 9:16 reel or short, 4:3 doc or design

const IMAGE = /\.(png|jpe?g|gif|webp|avif)$/i
const VIDEO = /\.(mp4|webm|mov|m4v)$/i

export function embedFor(raw: string): Embed {
  let u: URL
  try {
    u = new URL(raw)
  } catch {
    return { kind: 'link', provider: 'Link' }
  }
  const host = u.hostname.replace(/^(www|m)\./, '')
  const path = u.pathname
  const seg = path.split('/').filter(Boolean)
  const frame = (src: string, provider: string, shape: Shape, verb: 'Play' | 'Preview' = 'Play', thumb?: string): Embed => ({
    kind: 'frame', src, provider, shape, verb, thumb,
  })

  // YouTube: watch?v=, youtu.be/, shorts/, embed/, live/
  if (host === 'youtube.com' || host === 'youtu.be' || host === 'music.youtube.com') {
    const id =
      host === 'youtu.be' ? seg[0] : u.searchParams.get('v') ?? (['shorts', 'embed', 'live'].includes(seg[0]) ? seg[1] : undefined)
    if (id && /^[\w-]{6,}$/.test(id)) {
      const start = parseInt(u.searchParams.get('t') ?? '', 10)
      const src = `https://www.youtube-nocookie.com/embed/${id}?rel=0${start > 0 ? `&start=${start}` : ''}`
      return frame(src, 'YouTube', seg[0] === 'shorts' ? 'tall' : 'wide', 'Play', `https://i.ytimg.com/vi/${id}/hqdefault.jpg`)
    }
  }
  if (host === 'vimeo.com' && /^\d+$/.test(seg[0] ?? '')) return frame(`https://player.vimeo.com/video/${seg[0]}`, 'Vimeo', 'wide')
  if (host === 'loom.com' && seg[0] === 'share' && seg[1]) return frame(`https://www.loom.com/embed/${seg[1]}`, 'Loom', 'wide')

  // Google Drive files (videos, images, PDFs) and Docs / Slides / Sheets: their /preview pages embed
  if (host === 'drive.google.com') {
    const id = seg[0] === 'file' && seg[1] === 'd' ? seg[2] : u.searchParams.get('id')
    if (id) return frame(`https://drive.google.com/file/d/${id}/preview`, 'Google Drive', 'wide', 'Preview')
  }
  if (host === 'docs.google.com' && seg[1] === 'd' && seg[2]) {
    const kinds: Record<string, string> = { document: 'Google Docs', presentation: 'Google Slides', spreadsheets: 'Google Sheets' }
    if (kinds[seg[0]]) return frame(`https://docs.google.com/${seg[0]}/d/${seg[2]}/preview`, kinds[seg[0]], 'page', 'Preview')
  }

  // Instagram posts and reels, TikTok videos (public ones)
  if (host === 'instagram.com' && ['p', 'reel', 'reels', 'tv'].includes(seg[0]) && seg[1])
    return frame(`https://www.instagram.com/${seg[0] === 'reels' ? 'reel' : seg[0]}/${seg[1]}/embed`, 'Instagram', 'tall')
  if (host === 'tiktok.com') {
    const i = seg.indexOf('video')
    if (i >= 0 && /^\d+$/.test(seg[i + 1] ?? '')) return frame(`https://www.tiktok.com/embed/v2/${seg[i + 1]}`, 'TikTok', 'tall')
  }

  // Canva: a "view" link embeds when the design is shared with anyone who has the link
  if (host === 'canva.com' && seg[0] === 'design' && seg[1] && seg[2])
    return frame(`https://www.canva.com/design/${seg[1]}/${seg[2]}/view?embed`, 'Canva', 'page', 'Preview')

  if (IMAGE.test(path)) return { kind: 'image', src: raw, provider: host }
  if (VIDEO.test(path)) return { kind: 'video', src: raw, provider: host }
  return { kind: 'link', provider: host }
}

/** "drive.google.com/file/d/…" for showing a link in a line. */
export function shortLink(url: string): string {
  try {
    const u = new URL(url)
    const rest = `${u.pathname}${u.search}`.replace(/\/$/, '')
    const text = `${u.hostname.replace(/^www\./, '')}${rest}`
    return text.length > 60 ? `${text.slice(0, 57)}…` : text
  } catch {
    return url
  }
}

/** Under the result field: what works, and why it's worth adding. */
export const RESULT_HINT = 'A YouTube, Google Drive, Canva or Instagram link works. The next person gets it with their turn.'

/** A web link, or a message saying what's wrong with it. Empty is fine (the link is optional). */
export function checkLink(url: string): string | undefined {
  const v = url.trim()
  if (!v) return undefined
  try {
    const u = new URL(v)
    if (u.protocol === 'http:' || u.protocol === 'https:') return undefined
  } catch {
    /* falls through */
  }
  return 'Paste a full web link, starting with https://'
}
