// The only import components use for data: the real backend (see contract.js).
//   getKpis(dashboardId)        -> Promise<DashboardResponse>
//   subscribe(eventType, onEvent) -> unsubscribe()
export { apiSource as dataSource } from './api/apiSource'
