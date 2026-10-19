import { useId, type ReactNode } from 'react'

/** An on/off setting: label (and a line of detail) on the left, the switch on the right. The whole row is the target. */
export function Switch(props: { label: ReactNode; detail?: ReactNode; checked: boolean; disabled?: boolean; onChange: (on: boolean) => void }) {
  const id = useId()
  return (
    <label className={`switch-row${props.disabled ? ' off' : ''}`} htmlFor={id}>
      <span className="switch-text">
        <span className="switch-label">{props.label}</span>
        {props.detail && <span className="switch-detail">{props.detail}</span>}
      </span>
      <input
        id={id}
        type="checkbox"
        role="switch"
        className="switch"
        checked={props.checked}
        disabled={props.disabled}
        onChange={(e) => props.onChange(e.target.checked)}
      />
    </label>
  )
}
