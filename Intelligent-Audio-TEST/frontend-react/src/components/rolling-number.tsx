import {
  animate,
  cancelFrame,
  frame,
  MotionConfigContext,
  useReducedMotion,
} from 'motion/react'
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffectEvent,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'

import { formatNumber } from '@/lib/format'

/**
 * 数字滚动（照搬 newAPI components/rolling-number.tsx：
 * 首次计数 0.6s + 数字位滚动 0.5s；prefers-reduced-motion 直落终值；
 * RollingNumberGroup 聚合同批动画。）
 */

type ProgressUpdate = (progress: number) => void
type StartNumberAnimation = (
  update: ProgressUpdate,
  duration: number,
  batch: string
) => () => void
type NumberAnimationBatch = {
  updates: Set<ProgressUpdate>
  duration: number
  stop?: () => void
}

const RollingNumberContext = createContext<StartNumberAnimation | null>(null)
const INITIAL_COUNT_DURATION = 0.6
const DIGIT_UPDATE_DURATION = 0.5

function animateNumberProgress(
  update: ProgressUpdate,
  duration: number
): () => void {
  const animation = animate(0, 1, {
    duration,
    // Even counting avoids a long pause at 13/14 or 22/23 for small totals.
    ease: duration === INITIAL_COUNT_DURATION ? 'linear' : [0.16, 1, 0.3, 1],
    onUpdate: update,
    onComplete: () => update(1),
  })
  return () => animation.stop()
}

/** A ready gate can collect asynchronous updates into one shared animation. */
export function RollingNumberGroup(props: {
  children: ReactNode
  ready?: boolean
}) {
  const ready = useRef(props.ready !== false)
  const pending = useRef(new Map<string, NumberAnimationBatch>())
  const running = useRef(new Set<NumberAnimationBatch>())
  const flush = useCallback(() => {
    if (!ready.current) return
    const batches = [...pending.current.values()]
    pending.current.clear()
    for (const batch of batches) {
      running.current.add(batch)
      batch.stop = animateNumberProgress((progress) => {
        for (const update of batch.updates) update(progress)
        if (progress >= 1) running.current.delete(batch)
      }, batch.duration)
    }
  }, [])
  const startAnimation = useCallback<StartNumberAnimation>(
    (update, duration, batch) => {
      const key = `${batch}:${duration}`
      let queued = pending.current.get(key)
      if (!queued) {
        queued = { updates: new Set(), duration }
        pending.current.set(key, queued)
      }
      queued.updates.add(update)
      if (ready.current) frame.update(flush)
      return () => {
        queued.updates.delete(update)
        if (queued.updates.size) return
        queued.stop?.()
        running.current.delete(queued)
        if (pending.current.get(key) === queued) pending.current.delete(key)
      }
    },
    [flush]
  )
  useLayoutEffect(() => {
    ready.current = props.ready !== false
    if (ready.current) frame.update(flush)
    else cancelFrame(flush)
  }, [props.ready, flush])
  useLayoutEffect(
    () => () => {
      cancelFrame(flush)
      for (const batch of running.current) batch.stop?.()
      running.current.clear()
      pending.current.clear()
    },
    [flush]
  )
  return (
    <RollingNumberContext value={startAnimation}>
      {props.children}
    </RollingNumberContext>
  )
}

/** Slides only changed glyphs; formatted separators and unchanged digits stay still. */
function RollingDigits(props: {
  from: string
  to: string
  direction: number
  batch: string
  onComplete: () => void
}) {
  const group = useContext(RollingNumberContext)
  const visual = useRef<HTMLSpanElement>(null)
  const complete = useEffectEvent(props.onComplete)
  useLayoutEffect(() => {
    const tracks = [
      ...(visual.current?.querySelectorAll<HTMLElement>(
        '[data-rolling-track]'
      ) ?? []),
    ]
    let finished = false
    const update = (progress: number) => {
      if (finished) return
      const offset = props.direction > 0 ? -50 * progress : -50 + 50 * progress
      for (const track of tracks) {
        track.style.transform = `translateY(${offset}%)`
      }
      if (progress >= 1) {
        finished = true
        complete()
      }
    }
    update(0)
    if (group) return group(update, DIGIT_UPDATE_DURATION, props.batch)
    return animateNumberProgress(update, DIGIT_UPDATE_DURATION)
  }, [props.from, props.to, props.direction, props.batch, group])
  const previousDigits = props.from.match(/[0-9]/g) ?? []
  let remaining = props.to.match(/[0-9]/g)?.length ?? 0
  let exitingDigits = previousDigits.length - remaining
  let exitingPrefix = ''
  if (exitingDigits > 0) {
    for (const token of props.from.match(/[0-9]|[^0-9]+/g) ?? []) {
      if (!exitingPrefix && !/[0-9]/.test(token)) continue
      if (/[0-9]/.test(token)) {
        if (exitingDigits === 0) break
        exitingDigits--
      }
      exitingPrefix += token
    }
  }
  const exitingGlyphs = [
    { key: 'previous', text: exitingPrefix },
    { key: 'blank', text: ' ' },
  ]
  if (props.direction < 0) exitingGlyphs.reverse()
  return (
    <span ref={visual} className='inline-flex items-baseline align-baseline'>
      {exitingPrefix && (
        <span className='relative inline-block overflow-hidden'>
          <span className='invisible'>{exitingPrefix}</span>
          <span
            data-rolling-track
            className='absolute inset-x-0 top-0 flex flex-col'
          >
            {exitingGlyphs.map((glyph) => (
              <span key={glyph.key} className='shrink-0'>
                {glyph.text}
              </span>
            ))}
          </span>
        </span>
      )}
      {(props.to.match(/[0-9]|[^0-9]+/g) ?? []).map((character) => {
        if (!/[0-9]/.test(character)) {
          return (
            <span key={`literal:${remaining}:${character}`}>{character}</span>
          )
        }
        const position = --remaining
        const previous =
          previousDigits[previousDigits.length - position - 1] ?? ' '
        if (previous === character) {
          return (
            <span key={`digit:${position}`} data-rolling-digit>
              {character}
            </span>
          )
        }
        const glyphs =
          props.direction > 0 ? [previous, character] : [character, previous]
        return (
          <span
            key={`digit:${position}`}
            data-rolling-digit
            className='relative inline-block overflow-hidden'
          >
            <span className='invisible'>{character}</span>
            <span
              data-rolling-track
              className='absolute inset-x-0 top-0 flex flex-col'
            >
              {glyphs.map((glyph, row) => (
                <span key={row === 0 ? 'top' : 'bottom'} className='shrink-0'>
                  {glyph}
                </span>
              ))}
            </span>
          </span>
        )
      })}
    </span>
  )
}

interface RollingNumberProps {
  value: string | number
  numericValue?: number
  formatValue?: (value: number) => string
  /** Smallest visible increment, expressed in numericValue's units. */
  displayStep?: number
  /** Cards fed by the same data source share an animation batch. */
  batch?: string
}

/** Counts once, then transitions only the digits changed by fresh data. */
export function RollingNumber(props: RollingNumberProps) {
  const systemReduceMotion = useReducedMotion()
  const config = useContext(MotionConfigContext)
  const group = useContext(RollingNumberContext)
  const reduceMotion = systemReduceMotion || config.reducedMotion === 'always'
  const visual = useRef<HTMLSpanElement>(null)
  const displayedValue = useRef(0)
  const [settled, setSettled] = useState<{
    target: number
    text: string
  } | null>(null)
  const text = String(props.value)
  const target =
    props.numericValue ??
    (typeof props.value === 'number' ? props.value : Number.NaN)
  const hasTarget = Number.isFinite(target) && /[0-9]/.test(text)
  const displayStep = props.displayStep ?? 0.01
  const batch = props.batch ?? 'default'
  const formatValue = useEffectEvent((value: number) =>
    (props.formatValue ?? formatNumber)(value)
  )
  const renderValue = useEffectEvent((value: number) => {
    displayedValue.current = value
    if (visual.current) visual.current.textContent = formatValue(value)
  })

  useLayoutEffect(() => {
    if (!hasTarget) {
      displayedValue.current = 0
      setSettled(null)
      return
    }
    if (reduceMotion || settled?.target === target || settled?.text === text) {
      displayedValue.current = target
      if (settled?.target !== target || settled.text !== text) {
        setSettled({ target, text })
      }
      return
    }
    if (settled) return
    const start = displayedValue.current
    let finished = false
    const update = (progress: number) => {
      if (finished) return
      if (progress >= 1) {
        finished = true
        renderValue(target)
        if (visual.current) visual.current.textContent = text
        setSettled({ target, text })
        return
      }
      let value = start + (target - start) * progress
      if (start !== target && formatValue(value) === text) {
        const step = Math.min(Math.abs(target - start), displayStep)
        value = target - Math.sign(target - start) * step
      }
      renderValue(value)
    }
    update(0)
    if (group) return group(update, INITIAL_COUNT_DURATION, batch)
    return animateNumberProgress(update, INITIAL_COUNT_DURATION)
  }, [
    target,
    text,
    hasTarget,
    reduceMotion,
    displayStep,
    batch,
    group,
    settled,
  ])

  if (!hasTarget) return text
  if (reduceMotion) {
    return (
      <span role='img' aria-label={text}>
        {text}
      </span>
    )
  }
  const updating = settled && settled.target !== target && settled.text !== text
  return (
    <span role='img' aria-label={text} className='inline-block tabular-nums'>
      <span ref={visual} aria-hidden='true' className='whitespace-pre'>
        {updating ? (
          <RollingDigits
            from={settled.text}
            to={text}
            direction={Math.sign(target - settled.target)}
            batch={batch}
            onComplete={() => {
              displayedValue.current = target
              setSettled({ target, text })
            }}
          />
        ) : (
          text
        )}
      </span>
    </span>
  )
}
