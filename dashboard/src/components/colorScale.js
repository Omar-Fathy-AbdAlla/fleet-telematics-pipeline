// Maps a value to a red (bad) -> green (good) color. higherIsBetter = false flips the direction.
export function scaleColor(value, min, max, higherIsBetter = true) {
  const t = Math.min(1, Math.max(0, (value - min) / (max - min || 1)))
  const hue = (higherIsBetter ? t : 1 - t) * 120
  return `hsl(${Math.round(hue)}, 70%, 45%)`
}
