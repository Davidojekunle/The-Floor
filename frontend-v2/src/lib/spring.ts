/*
 * A tiny spring, parameterised the way Apple's design talks describe it:
 * - dampingRatio: 1 = no overshoot (the default for UI), below 1 = some bounce (only after a flick).
 * - response: roughly how quickly it gets there, in seconds. Not a duration: settling time emerges.
 * It starts from the current value and velocity, so a gesture can hand off to it without a seam,
 * and a new spring can start from wherever an interrupted one left off.
 */

export type SpringOptions = { dampingRatio?: number; response?: number; velocity?: number }

export type SpringHandle = { stop: () => void; value: () => number; velocity: () => number }

export function spring(
  from: number,
  to: number,
  onFrame: (value: number) => void,
  { dampingRatio = 1, response = 0.35, velocity = 0 }: SpringOptions = {},
  onDone?: () => void,
): SpringHandle {
  const stiffness = (2 * Math.PI / response) ** 2
  const damping = (4 * Math.PI * dampingRatio) / response
  let x = from
  let v = velocity
  let last = performance.now()
  let raf = 0

  const step = (now: number) => {
    // Integrate in small fixed steps so a dropped frame doesn't make it unstable.
    let dt = Math.min(0.064, (now - last) / 1000)
    last = now
    while (dt > 0) {
      const h = Math.min(dt, 1 / 240)
      const a = -stiffness * (x - to) - damping * v
      v += a * h
      x += v * h
      dt -= h
    }
    if (Math.abs(x - to) < 0.5 && Math.abs(v) < 5) {
      onFrame(to)
      raf = 0
      onDone?.()
      return
    }
    onFrame(x)
    raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)

  return {
    stop: () => {
      if (raf) cancelAnimationFrame(raf)
      raf = 0
    },
    value: () => x,
    velocity: () => v,
  }
}

/** Where a flick would come to rest (Apple's projection, the same curve as scroll deceleration). */
export function project(velocity: number, decelerationRate = 0.998): number {
  return ((velocity / 1000) * decelerationRate) / (1 - decelerationRate)
}

/** Soft resistance past an edge: the further you pull, the less it follows. */
export function rubberband(overshoot: number, dimension: number, constant = 0.55): number {
  return (overshoot * dimension * constant) / (dimension + constant * Math.abs(overshoot))
}
