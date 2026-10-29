// Real backend: warehouse KPIs + chart series over REST, live data over one shared SSE connection.
import { config } from '../../config'
import { DASHBOARDS_BY_ID } from '../../dashboards'

const subscriptions = new Set() // { eventType, listener } of every current subscriber
let eventSource = null
let reconnectScheduled = false

// One EventSource for all subscribers, asking only for their event types (?events=stream_kpis&events=alert...), so a
// page without the map does not download the ~4 MB map snapshot. It reconnects when the subscribers change, so every
// new subscriber gets the snapshot of its events, and closes when nobody listens. A page mounts all its subscribers in
// one go, so the reconnect waits for the end of it (microtask): one connection per page change, not one per subscriber.
// EventSource itself reconnects after a network drop, with the same URL.
function scheduleReconnect() {
  if (reconnectScheduled) return
  reconnectScheduled = true
  queueMicrotask(() => {
    reconnectScheduled = false
    eventSource?.close()
    eventSource = null
    const eventTypes = new Set([...subscriptions].map(({ eventType }) => eventType))
    if (eventTypes.size === 0) return
    const query = new URLSearchParams([...eventTypes].map((eventType) => ['events', eventType]))
    eventSource = new EventSource(`${config.streamUrl}?${query}`)
    for (const { eventType, listener } of subscriptions) eventSource.addEventListener(eventType, listener)
  })
}

// A page left by a full load stays in the browser's back/forward cache with its connection open, and the browser
// allows only 6 per host: after a few pages every request to the backend would wait. So the connection closes when the
// page is hidden, and opens again if the page comes back from that cache.
window.addEventListener('pagehide', () => {
  eventSource?.close()
  eventSource = null
})
window.addEventListener('pageshow', (event) => event.persisted && scheduleReconnect())

export const apiSource = {
  // dashboards.js is the only list of KPI ids per page: they are sent as ?kpi_ids=1&kpi_ids=2...
  async getKpis(dashboardId) {
    const query = new URLSearchParams(DASHBOARDS_BY_ID[dashboardId].kpiIds.map((kpiId) => ['kpi_ids', kpiId]))
    const response = await fetch(`${config.apiBaseUrl}/kpis/${dashboardId}?${query}`)
    if (!response.ok) throw new Error(`GET /kpis/${dashboardId} failed with status ${response.status}`)
    return response.json()
  },

  subscribe(eventType, onEvent) {
    const subscription = { eventType, listener: (message) => onEvent(JSON.parse(message.data)) }
    subscriptions.add(subscription)
    scheduleReconnect()
    return () => {
      subscriptions.delete(subscription)
      eventSource?.removeEventListener(eventType, subscription.listener) // no call after unmount, even before the reconnect
      scheduleReconnect()
    }
  },
}
