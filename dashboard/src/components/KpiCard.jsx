import { KPIS, formatValue } from '../kpis/definitions'

// Change vs previous period. % KPIs show the difference in percentage points (pp), others the relative change.
function Trend({ value, previous, unit, better }) {
  if (value == null || previous == null || value === previous) return <span className="text-slate-500">no change vs previous</span>
  const up = value > previous
  const good = better == null ? null : (better === 'up') === up
  const color = good == null ? 'text-slate-600 dark:text-slate-400' : good ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
  const change =
    unit === '%'
      ? `${Math.abs(value - previous).toFixed(1)} pp`
      : previous === 0
        ? ''
        : `${Math.abs(((value - previous) / previous) * 100).toFixed(1)}%`
  return (
    <span className={color}>
      {up ? '▲' : '▼'} {change} vs previous
    </span>
  )
}

export function KpiCard({ kpiId, value, previous }) {
  const kpi = KPIS[kpiId]
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900/60">
      <div className="text-xs font-medium text-slate-600 dark:text-slate-400">
        {kpi.name} <span className="text-slate-400 dark:text-slate-600">#{kpiId}</span>
      </div>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span className="text-2xl font-semibold text-slate-900 dark:text-slate-100">{formatValue(value, kpi.unit)}</span>
        <span className="text-sm text-slate-600 dark:text-slate-400">{kpi.unit}</span>
      </div>
      <div className="mt-1 text-xs">
        <Trend value={value} previous={previous} unit={kpi.unit} better={kpi.better} />
      </div>
      <p className="mt-2 text-xs leading-snug text-slate-500">{kpi.meaning}</p>
    </div>
  )
}

export function KpiGrid({ kpiIds, kpis }) {
  const byId = new Map(kpis.map((kpi) => [kpi.kpi_id, kpi]))
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {kpiIds.map((kpiId) => (
        <KpiCard key={kpiId} kpiId={kpiId} value={byId.get(kpiId)?.value} previous={byId.get(kpiId)?.previous} />
      ))}
    </div>
  )
}
