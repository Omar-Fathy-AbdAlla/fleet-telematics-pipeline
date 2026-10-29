import { useRef, useState } from 'react'
import { FACILITIES } from '../data/facilities'
import { ANOMALY_TYPES } from '../kpis/definitions'
import { useStream } from './useStream'

const FEED_SIZE = 40

// Display status of a truck. Anomalies come from backend alerts (no detection in the frontend).
// When a truck has several active anomalies, the first in this order wins.
const ANOMALY_PRIORITY = [
  'COLD_CHAIN_BREACH', 'REEFER_UNIT_FAILURE', 'ENGINE_OVERHEATING', 'ROUTE_DEVIATION', 'SPEEDING', 'LOW_FUEL', 'EXCESSIVE_IDLING',
]

// Labels of the motion_status values (silver stream column), also used by the Live KPI tiles.
export const MOTION_STATUS_LABEL = { DRIVING: 'Driving', IDLING: 'Idling', PARKED: 'Parked' }

// Without an anomaly, the status is the row's motion_status, with PARKED split by place (see statusOf).
export const STATUS_STYLE = {
  ...ANOMALY_TYPES,
  DRIVING: { label: MOTION_STATUS_LABEL.DRIVING, color: '#22c55e' },
  IDLING: { label: MOTION_STATUS_LABEL.IDLING, color: '#a3e635' },
  PARKED_AT_FACILITY: { label: 'Parked at facility', color: '#475569' },
  RESTING_ON_ROUTE: { label: 'Resting on route', color: '#94a3b8' },
}

// PARKED within this distance of a facility = at the facility (loading / waiting); farther = resting on the route
// (the 10-hour Hours-of-Service rest, catalog: rest breaks are only visible in telemetry).
const AT_FACILITY_MILES = 10
const MILES_PER_DEGREE = 69 // 1 degree of latitude

// Miles from a row's position to the nearest facility. Flat approximation: accurate enough at the 10-mi scale.
// Cached per row (rows are never changed), so re-renders do not repeat the 50-facility search.
const facilityMilesCache = new WeakMap()
function milesToNearestFacility(telemetry) {
  let miles = facilityMilesCache.get(telemetry)
  if (miles === undefined) {
    const cosLat = Math.cos((telemetry.lat * Math.PI) / 180)
    const degrees = FACILITIES.map((facility) => Math.hypot((facility.longitude - telemetry.lon) * cosLat, facility.latitude - telemetry.lat))
    miles = Math.min(...degrees) * MILES_PER_DEGREE
    facilityMilesCache.set(telemetry, miles)
  }
  return miles
}

// Real position = lat and lon both sent and inside the GPS range (catalog: null GPS = missing, validate ranges).
// A truck without one is not drawn on the map and is counted as "Position unknown".
export const hasPosition = ({ lat, lon }) => lat != null && lon != null && Math.abs(lat) <= 90 && Math.abs(lon) <= 180

// Needs a position (callers check hasPosition first): PARKED is split by the distance to the nearest facility.
export function statusOf(telemetry, anomalyTypes) {
  const anomaly = anomalyTypes && ANOMALY_PRIORITY.find((type) => anomalyTypes.has(type))
  if (anomaly) return anomaly
  if (telemetry.motion_status !== 'PARKED') return telemetry.motion_status
  return milesToNearestFacility(telemetry) <= AT_FACILITY_MILES ? 'PARKED_AT_FACILITY' : 'RESTING_ON_ROUTE'
}

// Live fleet picture built from the four stream events.
// Big data (5,000 trucks) lives in refs so the 3D scene can read it every frame without React re-renders;
// `tick` changes once per telemetry batch so side panels can refresh.
export function useFleetState() {
  const vehicles = useRef(new Map()) // vehicle_id -> { telemetry, reefer }
  const activeAlerts = useRef(new Map()) // anomaly_id -> AlertRow
  const dirty = useRef(false) // true when the 3D scene must redraw
  const [tick, setTick] = useState(0)
  const [alertFeed, setAlertFeed] = useState([])
  const [liveKpis, setLiveKpis] = useState(null) // LiveKpis, calculated by the backend
  // The snapshot ends with its kpis event. Alerts that arrive after it are new (the page lights them up); marked when the
  // message arrives, because React may draw the whole snapshot at once, after that kpis event.
  const snapshotDone = useRef(false)
  const newAlertIds = useRef(new Set()) // anomaly_id of the last FEED_SIZE alert changes after the snapshot

  useStream('telemetry', (rows) => {
    for (const row of rows) {
      const vehicle = vehicles.current.get(row.vehicle_id) ?? { telemetry: null, reefer: null }
      // Rows are kept as sent: null lat/lon = position unknown, so the truck is not drawn (no guessed position).
      vehicles.current.set(row.vehicle_id, { ...vehicle, telemetry: row })
    }
    dirty.current = true
    setTick((value) => value + 1)
  })

  useStream('reefer', (rows) => {
    for (const row of rows) {
      const vehicle = vehicles.current.get(row.vehicle_id) ?? { telemetry: null, reefer: null }
      vehicles.current.set(row.vehicle_id, { ...vehicle, reefer: row })
    }
  })

  useStream('alert', (alert) => {
    if (snapshotDone.current) {
      newAlertIds.current.add(alert.anomaly_id)
      if (newAlertIds.current.size > FEED_SIZE) newAlertIds.current.delete(newAlertIds.current.values().next().value)
    }
    if (alert.end_ts) activeAlerts.current.delete(alert.anomaly_id)
    else activeAlerts.current.set(alert.anomaly_id, alert)
    dirty.current = true
    // One row per anomaly: an "ended" update replaces its "started" row and moves to the top.
    setAlertFeed((feed) => [alert, ...feed.filter((row) => row.anomaly_id !== alert.anomaly_id)].slice(0, FEED_SIZE))
  })

  useStream('kpis', (kpis) => {
    snapshotDone.current = true
    setLiveKpis(kpis)
  })

  // vehicle_id -> Set of active anomaly types
  function activeTypesByVehicle() {
    const result = new Map()
    for (const alert of activeAlerts.current.values()) {
      if (!result.has(alert.vehicle_id)) result.set(alert.vehicle_id, new Set())
      result.get(alert.vehicle_id).add(alert.anomaly_type)
    }
    return result
  }

  return { vehicles, dirty, tick, alertFeed, liveKpis, newAlertIds, activeTypesByVehicle }
}
