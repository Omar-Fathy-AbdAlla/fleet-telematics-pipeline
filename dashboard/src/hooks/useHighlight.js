import { useEffect, useRef, useState } from 'react'

export const HIGHLIGHT_MS = 2000
const NOT_SEEN = Symbol('not seen')

// True for HIGHLIGHT_MS after `value` changes, so updated data lights up. The first value does not light up (that is
// the page loading), unless lightFirst (e.g. an alert row that appears after the page loaded). A new change while lit
// starts the 2 s again.
export function useHighlight(value, lightFirst = false) {
  const previous = useRef(lightFirst ? NOT_SEEN : value)
  const [lit, setLit] = useState(false)

  useEffect(() => {
    if (Object.is(previous.current, value)) return
    previous.current = value
    setLit(true)
  }, [value])

  useEffect(() => {
    if (!lit) return undefined
    const timer = setTimeout(() => setLit(false), HIGHLIGHT_MS)
    return () => clearTimeout(timer)
  }, [lit, value])

  return lit
}
