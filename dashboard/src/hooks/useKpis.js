import { useEffect, useState } from 'react'
import { dataSource } from '../data'
import { DASHBOARDS_BY_ID } from '../dashboards'

// Warehouse data changes slowly (batch loads), so pages re-fetch every 30 min. The live map streams instantly instead.
const REFRESH_MS = 30 * 60 * 1000

// Loads one dashboard's warehouse KPIs + chart series, then again every REFRESH_MS.
// While a refresh runs, the previous data stays on screen (loading is true only for the first load).
// A page without KPI cards (the live map: stream only) does not call the backend.
export function useKpis(dashboardId) {
  const hasKpis = DASHBOARDS_BY_ID[dashboardId].kpiIds.length > 0
  const [state, setState] = useState({ data: null, error: null, loading: hasKpis })

  useEffect(() => {
    if (!hasKpis) return undefined
    let cancelled = false
    setState({ data: null, error: null, loading: true })
    const load = () =>
      dataSource
        .getKpis(dashboardId)
        .then((data) => !cancelled && setState({ data, error: null, loading: false }))
        .catch((error) => !cancelled && setState((previous) => ({ ...previous, error, loading: false })))
    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [dashboardId, hasKpis])

  return state
}
