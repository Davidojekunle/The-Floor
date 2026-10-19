import { useEffect, useRef, useState } from 'react'
import { Icon } from '../components/Icon'
import { spring, type SpringHandle } from '../lib/spring'
import { prefersReducedMotion } from '../lib/useMedia'

type Status = 'locked' | 'todo' | 'in_progress' | 'done'
type Line = { id: number; text: string; live?: boolean }

const STAGES = [
  { title: 'Script', who: 'Femi', tag: 'Content Writer' },
  { title: 'Shoot', who: 'Tola', tag: 'Videographer' },
  { title: 'Edit', who: 'Kemi', tag: 'Video Editor' },
]
const START: Status[] = ['todo', 'locked', 'locked']
const FIRST_LINE: Line = { id: 0, text: 'Ada created Product promo video' }
const LABEL: Record<Status, string> = { locked: 'Locked', todo: 'To do', in_progress: 'In progress', done: 'Done' }

/**
 * The landing page's working demo: hand a task along its stages. The visitor presses Start / Mark done on
 * whichever stage is current, the next one unlocks, the progress bar follows on a spring (interruptible:
 * tap quickly and it re-targets from wherever it is, carrying its speed), and the room's activity fills in
 * the way it does in the real app.
 */
export function StageDemo() {
  const [status, setStatus] = useState<Status[]>(START)
  const [lines, setLines] = useState<Line[]>([FIRST_LINE])
  const seq = useRef(1)
  const bar = useRef<HTMLSpanElement>(null)
  const anim = useRef<SpringHandle | null>(null)
  const shown = useRef(0)

  const done = status.filter((s) => s === 'done').length
  const complete = done === STAGES.length

  // Progress follows a critically damped spring from wherever it is right now.
  useEffect(() => {
    const target = done / STAGES.length
    const draw = (v: number) => {
      shown.current = v
      if (bar.current) bar.current.style.transform = `scaleX(${v})`
    }
    if (prefersReducedMotion()) return draw(target)
    const velocity = anim.current?.velocity() ?? 0
    anim.current?.stop()
    anim.current = spring(shown.current, target, draw, { dampingRatio: 1, response: 0.45, velocity })
    return () => anim.current?.stop()
  }, [done])

  const say = (text: string, live = false) => setLines((all) => [...all, { id: seq.current++, text, live }].slice(-4))

  const act = (i: number) => {
    const s = STAGES[i]
    if (status[i] === 'todo') {
      setStatus((all) => all.map((x, j) => (j === i ? 'in_progress' : x)))
      say(`${s.who} started ${s.title}`)
      return
    }
    const next = STAGES[i + 1]
    setStatus((all) => all.map((x, j) => (j === i ? 'done' : j === i + 1 ? 'todo' : x)))
    say(next ? `${s.who} finished ${s.title}. ${next.title} can start now, and ${next.who} sees it straight away.` : `Product promo video is complete`, true)
  }

  const reset = () => {
    setStatus(START)
    setLines([FIRST_LINE])
  }

  return (
    <div className="demo" aria-label="Try it: hand a task along its stages">
      <div className="demo-card">
        <div className="demo-head">
          <div>
            <p className="demo-eyebrow">Studio Alpha</p>
            <h3>Product promo video</h3>
          </div>
          <span className={`demo-pill ${complete ? 'done' : ''}`}>{complete ? 'Complete' : `${done} of 3 done`}</span>
        </div>
        <div className="demo-bar" aria-hidden="true">
          <span ref={bar} />
        </div>

        <ol className="demo-stages">
          {STAGES.map((s, i) => {
            const st = status[i]
            return (
              <li key={s.title} className={`demo-stage is-${st}`}>
                <span className="demo-marker" aria-hidden="true">
                  {st === 'done' && <Icon name="check" size={12} bold />}
                </span>
                <div className="demo-stage-body">
                  <div className="demo-stage-top">
                    <strong>{s.title}</strong>
                    <span className={`demo-status ${st}`}>{LABEL[st]}</span>
                  </div>
                  <span className="demo-who">
                    <span className="demo-tag">{s.tag}</span> {s.who}
                  </span>
                  {st === 'locked' && <span className="demo-wait">Starts when {STAGES[i - 1].title} is done</span>}
                </div>
                {(st === 'todo' || st === 'in_progress') && (
                  <button type="button" className="btn primary sm demo-act" onClick={() => act(i)}>
                    {st === 'todo' ? 'Start' : (
                      <>
                        <Icon name="check" /> Mark done
                      </>
                    )}
                  </button>
                )}
              </li>
            )
          })}
        </ol>
      </div>

      <div className="demo-foot">
        {complete ? (
          <button type="button" className="link-btn" onClick={reset}>
            Run it again
          </button>
        ) : (
          <span>Try it: press the green button.</span>
        )}
      </div>
      <div className="demo-feed" aria-live="polite" aria-label="Room activity">
        {lines.map((l) => (
          <p key={l.id} className={`demo-line${l.live ? ' live' : ''}`}>
            <span className="demo-ico" aria-hidden="true">
              <Icon name="bolt" size={11} />
            </span>
            {l.text}
          </p>
        ))}
      </div>

    </div>
  )
}
