import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useTheme } from '../hooks/useTheme'
import { columnLabel } from '../kpis/definitions'
import NoData from './NoData'

const COLORS = ['#38bdf8', '#a78bfa', '#34d399', '#fbbf24', '#f87171']
const AXIS = { stroke: '#64748b', fontSize: 11, tickLine: false }
// Grid, tooltip and band-label colors per theme (series colors are the same in both).
const CHROME = {
  light: { grid: '#e2e8f0', tooltipBg: '#ffffff', tooltipBorder: '#cbd5e1', tooltipLabel: '#334155', bandLabel: '#16a34a' },
  dark: { grid: '#1e293b', tooltipBg: '#0f172a', tooltipBorder: '#334155', tooltipLabel: '#cbd5e1', bandLabel: '#4ade80' },
}
const tooltipProps = (chrome) => ({
  contentStyle: { background: chrome.tooltipBg, border: `1px solid ${chrome.tooltipBorder}`, borderRadius: 8, fontSize: 12 },
  labelStyle: { color: chrome.tooltipLabel },
  // warehouse values are not rounded (e.g. 93.3726): show at most 2 decimals
  formatter: (value) => (typeof value === 'number' ? value.toLocaleString('en-US', { maximumFractionDigits: 2 }) : value),
})
const MARGIN = { top: 8, right: 16, bottom: 0, left: 0 }

// series items: { key, label?, color? }. label defaults to KPI name + unit for kpi_<id> keys.
const withDefaults = (series) =>
  series.map((item, index) => ({ ...item, label: item.label ?? columnLabel(item.key), color: item.color ?? COLORS[index % COLORS.length] }))

// band = { min, max, label } draws an "allowed range" area (e.g. cold-chain limits).
// xFormat = optional (x value) => text for the x axis and tooltip (e.g. hhmm for event_ts).
export function LineChartView({ data, xKey, lines, band, xFormat, height = 260 }) {
  const chrome = CHROME[useTheme().theme]
  if (!data?.length) return <NoData />
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={MARGIN}>
        <CartesianGrid stroke={chrome.grid} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={xFormat} />
        <YAxis {...AXIS} domain={['auto', 'auto']} width={56} />
        <Tooltip {...tooltipProps(chrome)} labelFormatter={xFormat} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {band && (
          <ReferenceArea
            y1={band.min}
            y2={band.max}
            ifOverflow="extendDomain"
            fill="#22c55e"
            fillOpacity={0.08}
            stroke="#22c55e"
            strokeOpacity={0.3}
            label={{ value: band.label, fill: chrome.bandLabel, fontSize: 11, position: 'insideTopLeft' }}
          />
        )}
        {withDefaults(lines).map((line) => (
          <Line key={line.key} dataKey={line.key} name={line.label} stroke={line.color} strokeWidth={2} dot={false} isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

// layout 'vertical' = horizontal bars, best for rankings with long names.
export function BarChartView({ data, xKey, bars, layout = 'horizontal', stacked = false, height = 260 }) {
  const vertical = layout === 'vertical'
  const chrome = CHROME[useTheme().theme]
  if (!data?.length) return <NoData />
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout={layout} margin={MARGIN}>
        <CartesianGrid stroke={chrome.grid} horizontal={!vertical} vertical={vertical} />
        <XAxis {...AXIS} type={vertical ? 'number' : 'category'} dataKey={vertical ? undefined : xKey} />
        <YAxis {...AXIS} type={vertical ? 'category' : 'number'} dataKey={vertical ? xKey : undefined} width={vertical ? 170 : 56} />
        <Tooltip {...tooltipProps(chrome)} cursor={{ fill: chrome.grid }} />
        {bars.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {withDefaults(bars).map((bar) => (
          <Bar key={bar.key} dataKey={bar.key} name={bar.label} fill={bar.color} stackId={stacked ? 'stack' : undefined} isAnimationActive={false} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}
