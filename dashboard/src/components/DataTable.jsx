import { columnLabel } from '../kpis/definitions'
import NoData from './NoData'

const display = (value) => (value == null ? '-' : typeof value === 'number' ? value.toLocaleString('en-US') : String(value))

// columns: [{ key, label?, format?(value, row) }]. label defaults to KPI name + unit for kpi_<id> keys.
export default function DataTable({ columns, rows }) {
  if (!rows?.length) return <NoData />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-slate-200 text-slate-600 dark:border-slate-800 dark:text-slate-400">
            {columns.map((column) => (
              <th key={column.key} className="px-2 py-2 font-medium">
                {column.label ?? columnLabel(column.key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-slate-100 text-slate-700 hover:bg-slate-50 dark:border-slate-800/60 dark:text-slate-300 dark:hover:bg-slate-800/40">
              {columns.map((column) => (
                <td key={column.key} className="whitespace-nowrap px-2 py-1.5">
                  {column.format ? column.format(row[column.key], row) : display(row[column.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
