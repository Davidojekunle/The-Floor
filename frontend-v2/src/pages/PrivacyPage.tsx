import { Link } from 'react-router-dom'
import { Logo } from '../components/Logo'
import { SUPPORT_EMAIL } from '../lib/support'

/** What The Floor stores, who sees it, and how to have it deleted. Public: linked from the landing page and sign-up. */
export function PrivacyPage() {
  return (
    <div className="legal">
      <header className="legal-head">
        <Link to="/" aria-label="The Floor, home">
          <Logo />
        </Link>
      </header>
      <main className="legal-body">
        <h1>Privacy</h1>
        <p className="faint">Last updated 21 October 2026</p>

        <p className="legal-lead">
          The Floor keeps only what it needs to run your rooms. It doesn't sell your data, show ads, or track you around
          the web.
        </p>

        <h2>What we store</h2>
        <ul>
          <li>
            <strong>Your account:</strong> your name, email address, time zone and theme. Your password is stored only as a
            secure hash, so nobody can read it, including us.
          </li>
          <li>
            <strong>Your work:</strong> the rooms you're in, your role and tags, tasks, stages and due dates, progress
            updates, result links, and chat messages.
          </li>
          <li>
            <strong>Notifications</strong> sent to you. They're deleted automatically after 90 days.
          </li>
          <li>
            <strong>If you turn them on:</strong> a push notification address from your browser (with the browser's name),
            and a private calendar link.
          </li>
          <li>
            <strong>Sign-in sessions,</strong> so you stay signed in for up to 30 days on each device.
          </li>
        </ul>
        <p>
          We don't store your location, your contacts, or any files. A result is a link; the file stays wherever you put it,
          such as Google Drive or YouTube. Our hosting provider keeps short-lived logs of requests, including IP
          addresses, to keep the service running and secure.
        </p>

        <h2>Who can see it</h2>
        <ul>
          <li>People in a room see your name, your work in that room, and the room's chat. People outside the room see none of it.</li>
          <li>Heads of a room can manage its members, tags and tasks.</li>
          <li>
            The people who run The Floor can access the database to keep it working and fix problems, and only do so when
            needed. The admin page they use shows totals only, never names, tasks or messages.
          </li>
        </ul>

        <h2>Services we use</h2>
        <ul>
          <li>
            <strong>Hosting and email providers</strong> run the app, store the database in the European Union, and send
            our emails, such as password resets and notifications.
          </li>
          <li>
            <strong>Your browser's push service</strong> (Google, Apple or Mozilla) delivers notifications, only if you turn
            them on.
          </li>
          <li>
            <strong>YouTube, Google Drive, Canva and similar sites</strong> load a result's preview only when you press
            play or preview on it.
          </li>
        </ul>

        <h2>Cookies and browser storage</h2>
        <p>
          One cookie keeps you signed in. Your browser also remembers a few settings, such as your theme and the last room
          you opened. There are no analytics or advertising cookies.
        </p>

        <h2>Your choices</h2>
        <ul>
          <li>Change your name, email and password in Account settings, and turn each kind of notification on or off.</li>
          <li>Leave a room at any time. You can delete your own chat messages.</li>
          <li>
            You can ask to see, correct or delete your data, as the Nigeria Data Protection Act 2023 and similar laws allow.
            To delete your account and everything linked to it, email{' '}
            <a href={`mailto:${SUPPORT_EMAIL}?subject=Delete%20my%20account`}>{SUPPORT_EMAIL}</a> from the address you
            signed up with. We'll do it within 30 days.
          </li>
        </ul>

        <h2>Security</h2>
        <p>
          Everything travels over an encrypted connection. Passwords are hashed, sign-in attempts are rate limited, and
          every request is checked against the rooms you belong to.
        </p>

        <h2>Questions</h2>
        <p>
          Email <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>. If this page changes, the date at the top changes
          with it.
        </p>
      </main>
    </div>
  )
}
