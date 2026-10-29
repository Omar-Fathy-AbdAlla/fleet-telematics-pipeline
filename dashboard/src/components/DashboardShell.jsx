import { useState } from 'react'
import { DASHBOARDS_BY_ID } from '../dashboards'
import { useKpis } from '../hooks/useKpis'
import { useStream } from '../hooks/useStream'
import { dateTime } from './format'
import InfoTip from './InfoTip'
import { KpiGrid } from './KpiCard'
import ThemeToggle from './ThemeToggle'

// Period labels with an info icon that explains, on hover or keyboard focus, what the card numbers and arrows compare.
// streamPeriod is shown only when the page has a card or chart from the live stream.
function PeriodInfo({ period, streamPeriod }) {
  return (
    <div className="flex items-center gap-1 text-xs text-slate-500">
      <div className="text-right">
        <div>{period}</div>
        {streamPeriod && <div>Live (Kafka): {streamPeriod}</div>}
      </div>
      <InfoTip label="What does the period mean?">
        The big number on each card is for the <b>current period</b>.
        <br />
        The ▲▼ arrow shows the change vs the <b>previous period</b> (pp = percentage points, for % KPIs).
        {streamPeriod && (
          <>
            <br />
            Cards and charts from the live stream (Kafka) use the <b>Live</b> period.
          </>
        )}
      </InfoTip>
    </div>
  )
}

// Stream values replace what the warehouse returns as null (the backend never sends one KPI or series from both).
function mergeStream(data, stream) {
  if (!stream) return { kpis: data.kpis, series: data.series, streamIds: new Set() }
  const streamIds = new Set(stream.kpis.map((kpi) => kpi.kpi_id))
  return {
    kpis: [...data.kpis.filter((kpi) => !streamIds.has(kpi.kpi_id)), ...stream.kpis],
    series: { ...data.series, ...stream.series },
    streamIds,
  }
}

// Common page frame: title, loading/error, KPI cards, then the page's charts.
// Warehouse KPIs come from useKpis (REST), stream KPIs from the stream_kpis event (SSE); the page gets them merged.
// children can be a function (series) => charts (rendered once data is loaded) or plain elements (always rendered).
export default function DashboardShell({ dashboardId, children }) {
  const dashboard = DASHBOARDS_BY_ID[dashboardId]
  const { data, error, loading } = useKpis(dashboardId)
  const [stream, setStream] = useState(null) // StreamKpis (contract.js), the latest one received
  useStream('stream_kpis', setStream)

  const merged = data && mergeStream(data, stream)
  const usesStream =
    Boolean(merged && stream) &&
    (dashboard.kpiIds.some((kpiId) => merged.streamIds.has(kpiId)) || Object.keys(data.series).some((key) => key in stream.series))

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{dashboard.title}</h1>
          <p className="text-xs text-slate-500">Audience: {dashboard.audience}</p>
        </div>
        <div className="flex items-center gap-4">
          {data && (
            <>
              <PeriodInfo period={data.period} streamPeriod={usesStream ? stream.period : null} />
              <div className="text-right">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Last updated</div>
                <div className="text-sm font-semibold text-slate-800 dark:text-slate-200">{dateTime(data.as_of)}</div>
              </div>
            </>
          )}
          <ThemeToggle />
        </div>
      </header>

      {loading && <p className="text-sm text-slate-600 dark:text-slate-400">Loading…</p>}
      {error && (
        <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-300">
          Could not load data: {error.message}
        </p>
      )}
      {merged && <KpiGrid kpiIds={dashboard.kpiIds} kpis={merged.kpis} />}
      {typeof children === 'function' ? merged && children(merged.series) : children}
    </div>
  )
}
