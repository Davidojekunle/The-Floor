/** Where feedback and privacy requests go. Forwarded to the team's inbox. */
export const SUPPORT_EMAIL = 'support@thefloorapp.me'

/** A mailto link for feedback, with the page it was sent from filled in. */
export function feedbackHref(page = typeof window !== 'undefined' ? window.location.pathname : '') {
  const body = `\n\n---\nSent from: ${page}`
  return `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('Feedback on The Floor')}&body=${encodeURIComponent(body)}`
}
