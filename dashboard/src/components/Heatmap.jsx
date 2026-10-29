import { scaleColor } from './colorScale'

// Grid of rowKey x colKey cells colored by valueKey (e.g. origin_city x destination_city on-time rate).
export default function Heatmap({ rows, rowKey, colKey, valueKey, min, max, unit, higherIsBetter = true }) {
  const rowValues = [...new Set(rows.map((row) => row[rowKey]))].sort()
  const colValues = [...new Set(rows.map((row) => row[colKey]))].sort()
  const cells = new Map(rows.map((row) => [`${row[rowKey]}|${row[colKey]}`, row[valueKey]]))

  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-0.5 text-[10px]">
        <thead>
          <tr>
            <th className="sticky left-0 bg-white pr-2 text-left align-bottom font-normal text-slate-500 dark:bg-slate-900">
              {rowKey} ↓ / {colKey} →
            </th>
            {colValues.map((col) => (
              <th key={col} className="h-24 px-0.5 align-bottom font-normal text-slate-600 dark:text-slate-400">
                <div className="rotate-180 [writing-mode:vertical-rl]">{col}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rowValues.map((rowValue) => (
            <tr key={rowValue}>
              <th className="sticky left-0 whitespace-nowrap bg-white pr-2 text-left font-normal text-slate-600 dark:bg-slate-900 dark:text-slate-400">{rowValue}</th>
              {colValues.map((col) => {
                const value = cells.get(`${rowValue}|${col}`)
                return (
                  <td
                    key={col}
                    title={value == null ? '' : `${rowValue} → ${col}: ${value} ${unit}`}
                    className="h-6 w-7 rounded-sm text-center text-white/90"
                    style={{ background: value == null ? 'transparent' : scaleColor(value, min, max, higherIsBetter) }}
                  >
                    {value == null ? '' : Math.round(value)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
