// Info icon button that shows children in a tooltip on hover or keyboard focus.
export default function InfoTip({ label, children }) {
  return (
    <span className="group relative inline-flex">
      <button type="button" aria-label={label} className="cursor-help text-slate-500 hover:text-slate-700 dark:hover:text-slate-300">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4" />
          <path d="M12 8h.01" />
        </svg>
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute right-0 top-full z-10 mt-2 hidden w-72 rounded-lg border border-slate-200 bg-white p-3 text-xs font-normal leading-relaxed text-slate-700 shadow-lg group-hover:block group-focus-within:block dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
      >
        {children}
      </span>
    </span>
  )
}
