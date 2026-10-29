// Clickable legend / filter: one chip per item (color, label, count) that hides or shows it, plus Show all / Hide all.
// items = [{ key, label, color?, count, unit }]; hidden = Set of hidden keys; onChange(next) gets a NEW Set,
// so React sees the change.
export default function FilterChips({ title, items, hidden, onChange }) {
  function toggle(key) {
    const next = new Set(hidden)
    if (!next.delete(key)) next.add(key)
    onChange(next)
  }

  return (
    <div className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-semibold text-slate-900 dark:text-slate-100">{title}</span>
        <div className="flex gap-3 font-semibold">
          <button type="button" onClick={() => onChange(new Set())} className="underline">
            Show all
          </button>
          <button type="button" onClick={() => onChange(new Set(items.map((item) => item.key)))} className="underline">
            Hide all
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {items.map(({ key, label, color, count, unit }) => (
          <button
            key={key}
            type="button"
            aria-pressed={!hidden.has(key)}
            onClick={() => toggle(key)}
            className={`flex items-center gap-1.5 rounded border border-slate-200 px-2 py-0.5 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800 ${hidden.has(key) ? 'line-through opacity-40' : ''}`}
          >
            {color && <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: color }} />}
            {label}: <span className="text-slate-900 dark:text-slate-100">{count.toLocaleString('en-US')}</span> {unit}
          </button>
        ))}
      </div>
    </div>
  )
}
