import { Suspense, useState } from 'react'
import DashboardShell from '../components/DashboardShell'
import FilterChips from '../components/FilterChips'
import { dateTime, hhmm, yesNo } from '../components/format'
import MapOverlay from '../components/MapOverlay'
import Panel from '../components/Panel'
import { FACILITIES } from '../data/facilities'
import { MOTION_STATUS_LABEL, STATUS_STYLE, hasPosition, statusOf, useFleetState } from '../hooks/useFleetState'
import { useHighlight } from '../hooks/useHighlight'
import { ANOMALY_TYPES } from '../kpis/definitions'
import FacilityLayer from '../scene/FacilityLayer'
import MapCanvas from '../scene/MapCanvas'
import TruckLayer from '../scene/TruckLayer'

// Fields shown for the selected truck: [column, unit]. Names = stream columns (catalog 3.14 / 3.15 + silver columns).
const TELEMETRY_FIELDS = [
  ['event_ts', ''], ['motion_status', ''], ['engine_on', ''], ['speed_mph', 'mph'], ['rpm', 'rpm'], ['engine_temp_f', '°F'],
  ['fuel_gph', 'gal/h'], ['fuel_level_gal', 'gal'], ['odometer_mi', 'mi'], ['lat', '°'], ['lon', '°'],
]
const REEFER_FIELDS = [
  ['trailer_id', ''], ['commodity_type', ''], ['cargo_temp_f', '°F'], ['setpoint_f', '°F'], ['allowed_temp_min_f', '°F'],
  ['allowed_temp_max_f', '°F'], ['compressor_on', ''], ['door_open', ''], ['ambient_temp_f', '°F'],
]

// Live KPI tiles: [label, value, unit, note]. Values come calculated from the backend (LiveKpis in contract.js).
function liveKpiTiles(kpis) {
  const byCommodity = Object.entries(kpis.cold_chain_compliance_pct_by_commodity).map(([commodity, pct]) => `${commodity} ${pct} %`)
  return [
    ['Trucks reporting', kpis.trucks_reporting, 'trucks', 'Latest row in the kept history'],
    ...Object.entries(MOTION_STATUS_LABEL).map(([status, label]) => [label, kpis.motion_status[status] ?? 0, 'trucks', 'motion_status now']),
    ['Speeding', kpis.is_speeding, 'trucks', 'is_speeding now'],
    ['Engine overheating', kpis.is_engine_overheating, 'trucks', 'is_engine_overheating now'],
    ['Low fuel', kpis.is_low_fuel, 'trucks', 'is_low_fuel now'],
    ['Reefers reporting', kpis.reefers_reporting, 'reefers', 'Latest reefer row in the kept history'],
    ['Reefer unit failure', kpis.is_reefer_unit_failure, 'reefers', 'is_reefer_unit_failure now'],
    ['Cold-chain compliance', kpis.cold_chain_compliance_pct, '%', byCommodity.join(' · ') || 'No valid reading'],
    ['Data age', kpis.data_age_min, 'min', `Newest reading ${hhmm(kpis.newest_event_ts)}`],
  ]
}

// Tailwind classes of a value that just changed (lit for 2 s by useHighlight)
const LIT = 'border-sky-400 bg-sky-50 dark:border-sky-500 dark:bg-sky-950/60'

// One Live KPI tile; it lights up for 2 s when its value changes.
function LiveKpiTile({ label, value, unit, note }) {
  const lit = useHighlight(value)
  return (
    <div className={`rounded-lg border p-2 transition-colors duration-500 ${lit ? LIT : 'border-slate-200 dark:border-slate-800'}`}>
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="text-lg font-semibold text-slate-900 dark:text-slate-100">
        {value == null ? '-' : value.toLocaleString('en-US')} <span className="text-xs font-normal text-slate-500">{unit}</span>
      </div>
      <div className="text-[10px] leading-snug text-slate-500">{note}</div>
    </div>
  )
}

function LiveKpiPanel({ kpis }) {
  return (
    <Panel
      title="Live KPIs"
      subtitle={kpis ? `Calculated by the backend from the latest row of each truck. As of ${hhmm(kpis.as_of)}, last data received ${hhmm(kpis.last_received_at)}` : 'Waiting for the stream…'}
    >
      {kpis && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {liveKpiTiles(kpis).map(([label, value, unit, note]) => (
            <LiveKpiTile key={label} label={label} value={value} unit={unit} note={note} />
          ))}
        </div>
      )}
    </Panel>
  )
}

// counts = trucks drawn on the map per status; unknownPosition = trucks whose latest row has no real position (not drawn).
function countByStatus(fleet) {
  const activeTypes = fleet.activeTypesByVehicle()
  const counts = Object.fromEntries(Object.keys(STATUS_STYLE).map((status) => [status, 0]))
  let unknownPosition = 0
  for (const [vehicleId, { telemetry }] of fleet.vehicles.current) {
    if (!telemetry) continue
    if (hasPosition(telemetry)) counts[statusOf(telemetry, activeTypes.get(vehicleId))] += 1
    else unknownPosition += 1
  }
  return { counts, unknownPosition }
}

// Missing values are shown as "missing", never as 0 (catalog A.6).
function FieldRows({ row, fields }) {
  return fields.map(([column, unit]) => {
    const value = row[column]
    const text = typeof value === 'boolean' ? yesNo(value) : value == null ? 'missing'
      : column === 'event_ts' ? dateTime(value) : `${value}${unit ? ` ${unit}` : ''}`
    return (
      <div key={column} className="flex justify-between gap-2 border-b border-slate-100 py-1 dark:border-slate-800/60">
        <span className="text-slate-500">{column}</span>
        <span className="text-slate-800 dark:text-slate-200">{text}</span>
      </div>
    )
  })
}

// One alert feed row; it lights up for 2 s when the alert ends, and when it is new after the page loaded
// (lightFirst = the alert arrived after the snapshot, see newAlertIds in useFleetState).
function AlertFeedRow({ alert, lightFirst, onSelect }) {
  const lit = useHighlight(alert.end_ts, lightFirst)
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(alert.vehicle_id)}
        className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left transition-colors duration-500 hover:bg-slate-100 dark:hover:bg-slate-800 ${lit ? LIT : ''}`}
      >
        <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: ANOMALY_TYPES[alert.anomaly_type].color }} />
        <span className="flex-1 text-slate-700 dark:text-slate-300">
          {ANOMALY_TYPES[alert.anomaly_type].label} · {alert.vehicle_id}
        </span>
        <span className={alert.end_ts ? 'text-slate-500' : 'text-rose-600 dark:text-rose-300'}>
          {alert.end_ts ? `ended ${hhmm(alert.end_ts)}` : `active since ${hhmm(alert.start_ts)}`}
        </span>
      </button>
    </li>
  )
}

export default function LiveMapPage() {
  const fleet = useFleetState()
  const [selectedId, setSelectedId] = useState(null)
  const [hoveredFacility, setHoveredFacility] = useState(null)
  const [hiddenStatuses, setHiddenStatuses] = useState(() => new Set()) // legend filter: statuses not drawn on the map

  const { counts, unknownPosition } = countByStatus(fleet)
  const selected = selectedId && fleet.vehicles.current.get(selectedId)
  const selectedAnomalies = selectedId ? [...(fleet.activeTypesByVehicle().get(selectedId) ?? [])] : []
  const streamTime = fleet.vehicles.current.values().next().value?.telemetry?.event_ts

  return (
    <DashboardShell dashboardId="live">
      <div className="mb-4">
        <LiveKpiPanel kpis={fleet.liveKpis} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <Panel
          title="Live fleet"
          subtitle={`Drag to rotate · scroll to zoom · click a truck. Bigger trucks = active anomaly. Stream time: ${streamTime ? dateTime(streamTime) : 'waiting…'}`}
        >
          <div className="relative h-[60vh] min-h-[420px] overflow-hidden rounded-lg">
            <MapCanvas>
              <FacilityLayer onHover={setHoveredFacility} />
              <Suspense fallback={null}>
                <TruckLayer fleet={fleet} selectedId={selectedId} hiddenStatuses={hiddenStatuses} onSelect={setSelectedId} />
              </Suspense>
            </MapCanvas>
            {hoveredFacility && (
              <MapOverlay className="left-3 top-3">
                <div className="font-semibold text-slate-900 dark:text-slate-100">{hoveredFacility.facility_name}</div>
                <div>{hoveredFacility.facility_type} · {hoveredFacility.city}, {hoveredFacility.state_code}</div>
              </MapOverlay>
            )}
          </div>

          {/* Color legend + filter, under the map */}
          <div className="mt-3 space-y-2 text-xs text-slate-700 dark:text-slate-300">
            <FilterChips
              title="Truck color = status (click to show / hide)"
              items={Object.entries(STATUS_STYLE).map(([status, style]) => ({ key: status, label: style.label, color: style.color, count: counts[status], unit: 'trucks' }))}
              hidden={hiddenStatuses}
              onChange={setHiddenStatuses}
            />
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm border border-dashed border-slate-400" />
                Position unknown (not on map): <span className="text-slate-900 dark:text-slate-100">{unknownPosition.toLocaleString('en-US')}</span> trucks
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-sm bg-slate-700 dark:bg-slate-200" />
                Facility (building): <span className="text-slate-900 dark:text-slate-100">{FACILITIES.length}</span> facilities
              </span>
            </div>
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel title="Selected truck" subtitle={selectedId ?? 'Click a truck or an alert'}>
            {selected?.telemetry ? (
              <div className="text-xs">
                {selectedAnomalies.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {selectedAnomalies.map((type) => (
                      <span key={type} className="rounded px-1.5 py-0.5 text-[10px] font-semibold text-slate-950" style={{ background: ANOMALY_TYPES[type].color }}>
                        {ANOMALY_TYPES[type].label}
                      </span>
                    ))}
                  </div>
                )}
                <FieldRows row={selected.telemetry} fields={TELEMETRY_FIELDS} />
                {selected.reefer && (
                  <>
                    <div className="mt-3 mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Reefer</div>
                    <FieldRows row={selected.reefer} fields={REEFER_FIELDS} />
                  </>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-500">No truck selected.</p>
            )}
          </Panel>

          <Panel title="Alert feed" subtitle="Alerts made by the backend from the stream flags (newest first)">
            <ul className="max-h-[360px] space-y-1 overflow-y-auto text-xs">
              {fleet.alertFeed.length === 0 && <li className="text-slate-500">No alerts yet.</li>}
              {fleet.alertFeed.map((alert) => (
                <AlertFeedRow key={alert.anomaly_id} alert={alert} lightFirst={fleet.newAlertIds.current.has(alert.anomaly_id)} onSelect={setSelectedId} />
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </DashboardShell>
  )
}
