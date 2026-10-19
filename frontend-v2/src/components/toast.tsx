import { useCallback, useRef, useState, type ReactNode } from 'react'
import { ToastContext } from './toastContext'

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState('')
  const [visible, setVisible] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  const show = useCallback((msg: string) => {
    setMessage(msg)
    setVisible(true)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setVisible(false), 2600)
  }, [])

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className={`toast ${visible ? 'show' : ''}`} role="status" aria-live="polite">
        {message}
      </div>
    </ToastContext.Provider>
  )
}
