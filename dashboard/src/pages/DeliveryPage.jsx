import { useMemo, useState } from 'react'
import { BarChartView } from '../components/charts'
import { scaleColor } from '../components/colorScale'
import DashboardShell from '../components/DashboardShell'
import DataTable from '../components/DataTable'
import FilterChips from '../components/FilterChips'
import { lane } from '../components/format'
import Heatmap from '../components/Heatmap'
import MapOverlay from '../components/MapOverlay'
import Panel from '../components/Panel'
import { formatValue } from '../kpis/definitions'
import MapCanvas from '../scene/MapCanvas'
import RouteArcs from '../scene/RouteArcs'

// Lane OTD color scale bounds (%): below 80 = full red, 100 = full green.
const OTD_MIN = 80
const OTD_MAX = 100
// Taller arc = worse lane, so problem lanes stand out.
const arcHeight = (row) => 0.5 + (100 - row.kpi_1) * 0.3
const arcColor = (row) => scaleColor(row.kpi_1, OTD_MIN, OTD_MAX)
// Legend bar sampled from the same scale as the arcs, so legend and arcs always match.
const OTD_LEGEND_STOPS = [80, 85, 90, 95, 100]
const OTD_GRADIENT = `linear-gradient(to right, ${OTD_LEGEND_STOPS.map((value) => scaleColor(value, OTD_MIN, OTD_MAX)).join(', ')})`
// Lane filter bands of kpi_1 (%), ascending: a lane is in the first band whose `to` (exclusive) is above its kpi_1.
// colorAt = value whose arc color the chip shows.
const OTD_BANDS = [
  { label: 'below 85 %', to: 85, colorAt: 82.5 },
  { label: '85–90 %', to: 90, colorAt: 87.5 },
  { label: '90–95 %', to: 95, colorAt: 92.5 },
  { label: '95–100 %', to: Infinity, colorAt: 97.5 },
]
const bandOf = (row) => OTD_BANDS.find((band) => row.kpi_1 < band.to).label

// Filter chip items: lanes per band, lanes per origin_city (counts = all lanes, not changed by the other filter).
function filterItems(lanes) {
  const bands = OTD_BANDS.map((band) => ({
    key: band.label, label: band.label, color: scaleColor(band.colorAt, OTD_MIN, OTD_MAX),
    count: lanes.filter((row) => bandOf(row) === band.label).length, unit: 'lanes',
  }))
  const lanesPerOrigin = new Map()
  for (const row of lanes) lanesPerOrigin.set(row.origin_city, (lanesPerOrigin.get(row.origin_city) ?? 0) + 1)
  const origins = [...lanesPerOrigin].sort(([a], [b]) => a.localeCompare(b)).map(([city, count]) => ({ key: city, label: city, count, unit: 'lanes' }))
  return { bands, origins }
}

function LaneMap({ lanes }) {
  const [hovered, setHovered] = useState(null)
  const [hiddenBands, setHiddenBands] = useState(() => new Set())
  const [hiddenOrigins, setHiddenOrigins] = useState(() => new Set())
  const { bands, origins } = useMemo(() => filterItems(lanes), [lanes])
  // Drawn = band shown AND origin_city shown. Memoized: RouteArcs rebuilds its arcs only when this list changes (not on hover).
  const shownLanes = useMemo(
    () => lanes.filter((row) => !hiddenBands.has(bandOf(row)) && !hiddenOrigins.has(row.origin_city)),
    [lanes, hiddenBands, hiddenOrigins],
  )

  return (
    <>
      <div className="relative h-[460px] overflow-hidden rounded-lg">
        <MapCanvas>
          <RouteArcs lanes={shownLanes} heightOf={arcHeight} colorOf={arcColor} onHover={setHovered} />
        </MapCanvas>
        <LaneHoverBox hovered={hovered} />
      </div>

      {/* Color legend + filters, under the map */}
      <div className="mt-3 space-y-3 text-xs text-slate-700 dark:text-slate-300">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-slate-900 dark:text-slate-100">Arc color = on-time delivery (%)</span>
          <span>≤ {OTD_MIN}</span>
          <div className="h-2 w-44 rounded-sm" style={{ background: OTD_GRADIENT }} />
          <span>{OTD_MAX}</span>
          <span className="text-slate-500">· Showing {shownLanes.length.toLocaleString('en-US')} of {lanes.length.toLocaleString('en-US')} lanes</span>
        </div>
        <FilterChips title="On-time band (click to show / hide)" items={bands} hidden={hiddenBands} onChange={setHiddenBands} />
        <FilterChips title="Origin city (click to show / hide)" items={origins} hidden={hiddenOrigins} onChange={setHiddenOrigins} />
      </div>
    </>
  )
}

// Details of the pointed lane, on the map's top-left corner.
function LaneHoverBox({ hovered }) {
  return (
    <MapOverlay className="left-3 top-3">
      {hovered ? (
        <>
          <div className="font-semibold text-slate-900 dark:text-slate-100">{lane(hovered)}</div>
          <div>On-time delivery: {formatValue(hovered.kpi_1, '%')} %</div>
          <div>Deliveries: {hovered.deliveries.toLocaleString('en-US')}</div>
          <div>Typical distance: {formatValue(hovered.typical_distance_km, 'km')} km</div>
        </>
      ) : (
        'Hover a lane'
      )}
    </MapOverlay>
  )
}

export default function DeliveryPage() {
  return (
    <DashboardShell dashboardId="delivery">
      {(series) => (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel
            className="lg:col-span-2"
            title="Lanes in 3D: on-time delivery by lane"
            subtitle="Arc height and color = how late the lane is (tall + red = worst on-time %). Each direction is its own lane."
          >
            <LaneMap lanes={series.lane_otd} />
          </Panel>
          <Panel className="lg:col-span-2" title="Lane heatmap: on-time delivery (%)" subtitle="Rows = origin_city, columns = destination_city">
            <Heatmap rows={series.lane_otd} rowKey="origin_city" colKey="destination_city" valueKey="kpi_1" min={OTD_MIN} max={OTD_MAX} unit="%" />
          </Panel>
          <Panel title="Customers with the lowest on-time rate">
            <DataTable
              columns={[{ key: 'customer_name', label: 'customer_name' }, { key: 'customer_type', label: 'customer_type' }, { key: 'deliveries', label: 'deliveries (count)' }, { key: 'kpi_1' }]}
              rows={series.worst_customers}
            />
          </Panel>
          <Panel title="Average delay by hour of day" subtitle="Scheduled delivery hour, minutes">
            <BarChartView data={series.delay_by_hour} xKey="hour" bars={[{ key: 'kpi_3' }]} />
          </Panel>
          <Panel className="lg:col-span-2" title="Facilities with the longest destination queue" subtitle="Minutes waiting before unloading starts">
            <BarChartView data={series.facility_queue} xKey="facility_name" bars={[{ key: 'kpi_6' }]} layout="vertical" height={320} />
          </Panel>
        </div>
      )}
    </DashboardShell>
  )
}
