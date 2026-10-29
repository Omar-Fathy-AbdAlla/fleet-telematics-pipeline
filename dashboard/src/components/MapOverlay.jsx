// Box drawn over a 3D map (hover info, color legend). className sets the corner, e.g. "left-3 top-3".
// pointer-events-none so dragging / clicking still reaches the map underneath.
export default function MapOverlay({ className, children }) {
  return (
    <div className={`pointer-events-none absolute rounded-lg bg-white/90 px-3 py-2 text-xs text-slate-700 dark:bg-slate-900/90 dark:text-slate-300 ${className}`}>
      {children}
    </div>
  )
}
