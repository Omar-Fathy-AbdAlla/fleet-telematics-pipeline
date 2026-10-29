export default function Panel({ title, subtitle, className = '', children }) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900/60 ${className}`}>
      {title && <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">{title}</h2>}
      {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      <div className={title || subtitle ? 'mt-3' : ''}>{children}</div>
    </section>
  )
}
