// Prototype harness for the room-home task row. Dev-only: served by Vite at /prototypes/task-row.html,
// never imported by src/ and not part of `vite build`. Delete this folder once a variant is promoted.
import { StrictMode, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import '../../src/styles/tokens.css'
import '../../src/styles/base.css'
import '../../src/styles/components.css'
import '../../src/styles/app.css'
import '../../src/styles/shell.css'
import './proto.css'
import { Icon } from '../../src/components/Icon'
import { GROUPS, TASKS, groupOf } from './fixtures'
import { VARIANTS } from './variants'

const tz = Intl.DateTimeFormat().resolvedOptions().timeZone

function Page({ v }: { v: number }) {
  const { Row, listClass } = VARIANTS[v]
  const [showDone, setShowDone] = useState(false)
  return (
    <div className="container">
      <div className="page home">
        <div className="page-head">
          <div>
            <h1>Studio Alpha</h1>
            <p className="sub">14 members</p>
          </div>
          <a className="btn primary" href="#">
            <Icon name="plus" />
            New task
          </a>
        </div>
        <div className="home-grid">
          <div className="rail rail-top">
            <section className="rail-card" aria-label="Your next steps">
              <h3>Your next steps</h3>
              <div className="rail-rows">
                <div className="row">
                  <span className="dot status-in_progress" />
                  <div className="main">
                    <div className="title">Colour proofs</div>
                    <div className="meta">Spring catalogue print files</div>
                  </div>
                </div>
                <div className="row">
                  <span className="dot" />
                  <div className="main">
                    <div className="title">Copy review</div>
                    <div className="meta">Website footer refresh</div>
                  </div>
                </div>
              </div>
            </section>
          </div>
          <section className="section home-tasks" aria-label="Tasks">
            <div className="section-h">
              <h2>All tasks in this room</h2>
              <div className="seg" role="group" aria-label="Filter tasks">
                <button type="button" aria-pressed="true">All</button>
                <button type="button" aria-pressed="false">Involves me</button>
              </div>
            </div>
            {GROUPS.map(({ key, label }) => {
              const items = TASKS.filter((t) => groupOf(t) === key)
              if (!items.length) return null
              const collapsed = key === 'done' && !showDone
              return (
                <div className="task-group" key={key}>
                  {key === 'done' ? (
                    <button type="button" className="grp grp-btn" aria-expanded={showDone} onClick={() => setShowDone(!showDone)}>
                      <Icon name={showDone ? 'down' : 'chev'} size={14} />
                      {label} <span className="n">{items.length}</span>
                    </button>
                  ) : (
                    <h3 className={`grp ${key}`}>
                      {label} <span className="n">{items.length}</span>
                    </h3>
                  )}
                  {!collapsed && (
                    <div className={listClass}>
                      {items.map((t) => (
                        <Row key={t.id} task={t} tz={tz} />
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </section>
        </div>
      </div>
    </div>
  )
}

function Picker({ current, onPick }: { current: number; onPick: (i: number) => void }) {
  const nav = useRef<HTMLElement>(null)
  const items = useRef<(HTMLButtonElement | null)[]>([])
  const hl = useRef<HTMLSpanElement>(null)
  const [ready, setReady] = useState(false)

  useLayoutEffect(() => {
    const move = () => {
      const el = items.current[current]
      if (!el || !hl.current) return
      hl.current.style.width = el.offsetWidth + 'px'
      hl.current.style.transform = `translateX(${el.offsetLeft}px)`
    }
    move()
    window.addEventListener('resize', move)
    return () => window.removeEventListener('resize', move)
  }, [current])

  useEffect(() => {
    requestAnimationFrame(() => requestAnimationFrame(() => setReady(true)))
  }, [])

  return (
    <nav className="proto-picker" aria-label="Prototype variants" ref={nav} data-ready={ready || undefined}>
      <span className="proto-picker-highlight" aria-hidden="true" ref={hl} />
      {VARIANTS.map((v, i) => (
        <button
          key={v.name}
          ref={(el) => {
            items.current[i] = el
          }}
          className="proto-picker-item"
          data-active={i === current || undefined}
          aria-current={i === current ? 'true' : undefined}
          onClick={() => onPick(i)}
        >
          {v.name}
        </button>
      ))}
    </nav>
  )
}

function Harness() {
  const [v, setV] = useState(() => {
    const n = (parseInt(new URLSearchParams(location.search).get('v') ?? '', 10) || 1) - 1
    return n >= 0 && n < VARIANTS.length ? n : 0
  })

  useEffect(() => {
    const url = new URL(location.href)
    url.searchParams.set('v', String(v + 1))
    history.replaceState(null, '', url)
  }, [v])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const num = parseInt(e.key, 10)
      if (num >= 1 && num <= VARIANTS.length) setV(num - 1)
      else if (e.key === 'ArrowRight') setV((c) => (c + 1) % VARIANTS.length)
      else if (e.key === 'ArrowLeft') setV((c) => (c - 1 + VARIANTS.length) % VARIANTS.length)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  // Keyed so switching re-mounts the variant; the swap itself is instant.
  return (
    <>
      <Page key={v} v={v} />
      <Picker current={v} onPick={setV} />
    </>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Harness />
  </StrictMode>,
)
