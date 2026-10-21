import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Icon, type IconName } from '../components/Icon'
import { StageDemo } from './StageDemo'
import { useReveal } from './useReveal'

const STEPS = [
  {
    title: 'Make a room',
    body: 'One room per team or project. Share its invite link, and approve each person who asks to join.',
  },
  {
    title: 'Break work into stages',
    body: 'Script, then Shoot, then Edit. Give each stage a person, or a tag like "Video Editor" so anyone with it can pick it up.',
  },
  {
    title: 'Hand it along',
    body: 'When a stage is done, the next one unlocks and its people see it in My work, on their phone or desktop, straight away.',
  },
]

const FEATURES: { icon: IconName; title: string; body: string }[] = [
  { icon: 'layers', title: 'Stages that unlock in order', body: 'Nobody starts too early. Stages can also run side by side, and heads can unlock one early when they need to.' },
  { icon: 'inbox', title: 'Proposals', body: 'Members suggest tasks. Heads approve them, or send them back with a note to fix and resend.' },
  { icon: 'chat', title: 'Chat beside the work', body: 'One conversation per room. Link a task in a message, post progress notes on a stage, and finished stages announce themselves.' },
  { icon: 'bolt', title: 'Live on every screen', body: 'A stage marked done shows up for everyone at once. No refreshing, no "did you see my message?".' },
  { icon: 'task', title: 'My work', body: 'Everything waiting on you, across all your rooms, most urgent first. With a calendar when you need the week at a glance.' },
  { icon: 'users', title: 'Heads and temporary heads', body: 'Away for a week? Make someone a temporary head. Their extra rights end on their own.' },
]

/**
 * The public front door (signed-out visitors at "/"). One job: show what The Floor does, fast, and get
 * people into a room. The hero carries a working demo instead of a screenshot.
 */
export function LandingPage() {
  const root = useRef<HTMLDivElement>(null)
  const [scrolled, setScrolled] = useState(false)
  useReveal(root)

  // The bar's edge appears only once content actually slides under it.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <div className="landing" ref={root}>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className={`l-bar${scrolled ? ' scrolled' : ''}`}>
        <div className="l-wrap l-bar-inner">
          <Link to="/" className="logo" aria-label="The Floor, home">
            <span className="logo-mark" aria-hidden="true" />
            The Floor
          </Link>
          <nav className="l-nav" aria-label="On this page">
            <a href="#how">How it works</a>
            <a href="#features">Features</a>
          </nav>
          <span className="l-spacer" />
          <Link className="btn ghost sm" to="/login">
            Sign in
          </Link>
          <Link className="btn primary sm" to="/register">
            Get started
          </Link>
        </div>
      </header>

      <main id="main">
        <section className="l-hero" aria-labelledby="hero-title">
          <div className="l-wrap l-hero-grid">
            <div className="l-hero-copy">
              <p className="l-eyebrow">For teams that hand work along</p>
              <h1 id="hero-title" className="l-display">
                Every task,
                <br />
                stage by stage.
              </h1>
              <p className="l-lede">
                The Floor gives your group one room for its work. Break each task into stages, and the next person knows the moment
                it's their turn.
              </p>
              <div className="l-ctas">
                <Link className="btn primary l-cta" to="/register">
                  Create your room
                  <Icon name="chev" />
                </Link>
                <Link className="btn l-cta" to="/login">
                  Sign in
                </Link>
              </div>
              <InviteOpener />
            </div>
            <div className="l-hero-demo" data-reveal>
              <StageDemo />
            </div>
          </div>
        </section>

        <section className="l-section" id="how" aria-labelledby="how-title">
          <div className="l-wrap">
            <div className="l-section-head" data-reveal>
              <p className="l-eyebrow">How it works</p>
              <h2 id="how-title" className="l-title">
                Three steps, then it runs itself.
              </h2>
            </div>
            <ol className="l-steps">
              {STEPS.map((s, i) => (
                <li key={s.title} className="l-step" data-reveal style={{ transitionDelay: `${i * 60}ms` }}>
                  <span className="l-step-n" aria-hidden="true">
                    {i + 1}
                  </span>
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="l-section l-alt" id="features" aria-labelledby="features-title">
          <div className="l-wrap">
            <div className="l-section-head" data-reveal>
              <p className="l-eyebrow">Features</p>
              <h2 id="features-title" className="l-title">
                Built around who does what next.
              </h2>
            </div>
            <ul className="l-features">
              {FEATURES.map((f, i) => (
                <li key={f.title} className="l-feature" data-reveal style={{ transitionDelay: `${(i % 3) * 60}ms` }}>
                  <span className="l-feature-ico" aria-hidden="true">
                    <Icon name={f.icon} size={20} />
                  </span>
                  <h3>{f.title}</h3>
                  <p>{f.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="l-section l-final" aria-labelledby="final-title">
          <div className="l-wrap l-final-inner" data-reveal>
            <h2 id="final-title" className="l-title">
              Bring your team onto The Floor.
            </h2>
            <p className="l-lede">Make a room in a minute. You'll get a link to invite people, and you approve everyone who joins.</p>
            <div className="l-ctas center">
              <Link className="btn primary l-cta" to="/register">
                Create your room
                <Icon name="chev" />
              </Link>
              <Link className="btn l-cta" to="/login">
                I have an account
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="l-foot">
        <div className="l-wrap l-foot-inner">
          <span className="logo">
            <span className="logo-mark" aria-hidden="true" />
            The Floor
          </span>
          <nav aria-label="Account">
            <Link to="/login">Sign in</Link>
            <Link to="/register">Create an account</Link>
            <Link to="/privacy">Privacy</Link>
          </nav>
        </div>
      </footer>
    </div>
  )
}

/** "Have an invite link?" opens an inline field (shown only when asked for). Signing in comes after, then the invite. */
function InviteOpener() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    // Accept a full link or just the code: take the last path segment.
    const code = value.trim().replace(/[?#].*$/, '').replace(/\/+$/, '').split('/').pop() ?? ''
    if (!code) return setError('Paste the link someone sent you.')
    navigate(`/join/${encodeURIComponent(code)}`)
  }

  if (!open)
    return (
      <p className="l-invite-q">
        Have an invite link?{' '}
        <button type="button" className="link-btn" onClick={() => setOpen(true)}>
          Open it
        </button>
      </p>
    )

  return (
    <form className="l-invite" onSubmit={submit} noValidate>
      <label htmlFor="l-invite-input" className="sr-only">
        Invite link
      </label>
      <input
        id="l-invite-input"
        className="input"
        autoFocus
        inputMode="url"
        autoComplete="off"
        placeholder="Paste your invite link"
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? 'l-invite-err' : undefined}
        onChange={(e) => {
          setValue(e.target.value)
          setError(null)
        }}
      />
      <button className="btn" type="submit">
        Open
      </button>
      {error && (
        <span className="err" id="l-invite-err" role="alert">
          {error}
        </span>
      )}
    </form>
  )
}
