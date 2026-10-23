import { useEffect, useRef, useState, type InputHTMLAttributes } from 'react'
import { Icon } from './Icon'

/** A password field with a show/hide eye. Hidden by default, and hidden again when its form is submitted. */
export function PasswordInput(props: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  const [shown, setShown] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const form = input.current?.form
    if (!form) return
    const hide = () => setShown(false)
    form.addEventListener('submit', hide)
    return () => form.removeEventListener('submit', hide)
  }, [])

  return (
    <span className="pw-field">
      <input {...props} ref={input} className={props.className ?? 'input'} type={shown ? 'text' : 'password'} />
      <button
        type="button"
        className="pw-eye"
        aria-label="Show password"
        aria-pressed={shown}
        aria-controls={props.id}
        onClick={() => setShown((s) => !s)}
      >
        <Icon name={shown ? 'eyeOff' : 'eye'} size={18} />
      </button>
    </span>
  )
}
