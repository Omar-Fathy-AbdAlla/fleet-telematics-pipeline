import { BarChartView, LineChartView } from '../components/charts'
import DashboardShell from '../components/DashboardShell'
import DataTable from '../components/DataTable'
import { hhmm } from '../components/format'
import Panel from '../components/Panel'

export default function ColdChainPage() {
  return (
    <DashboardShell dashboardId="cold_chain">
      {(series) => {
        // From the live stream (stream_kpis): the trailer with the longest excursion in the window (Kafka has no trip_id).
        // null when the window has no excursion: the panel then shows "No data"
        const trip = series.trip_temperature
        return (
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel
              className="lg:col-span-2"
              title={trip ? `Cargo temperature: ${trip.trailer_id} (${trip.vehicle_id}, ${trip.commodity})` : 'Cargo temperature'}
              subtitle={
                trip &&
                `°F. Trailer with the longest excursion in the live window. Green band = allowed range ${trip.min_temp_f} to ${trip.max_temp_f} °F for ${trip.commodity}. Gaps = missing readings.`
              }
            >
              <LineChartView
                data={trip?.readings}
                xKey="event_ts"
                xFormat={hhmm}
                lines={[{ key: 'cargo_temp_f', label: 'cargo_temp_f (°F)' }, { key: 'setpoint_f', label: 'setpoint_f (°F)', color: '#64748b' }]}
                band={trip && { min: trip.min_temp_f, max: trip.max_temp_f, label: 'allowed range' }}
                height={300}
              />
            </Panel>
            <Panel title="Excursion rate by ambient temperature" subtitle="% of reefer trips with an excursion, per ambient_temp_f band (°F)">
              <BarChartView data={series.excursion_rate_by_ambient} xKey="ambient_band" bars={[{ key: 'kpi_17', color: '#f87171' }]} />
            </Panel>
            <Panel title="Trailers with the most excursions" subtitle="Count of excursions in the period: candidates for inspection">
              <BarChartView
                data={series.excursions_by_trailer}
                xKey="trailer_id"
                bars={[{ key: 'excursions', label: 'excursions (count)', color: '#06b6d4' }]}
                layout="vertical"
              />
            </Panel>
            <Panel className="lg:col-span-2" title="High-risk trips" subtitle="Longest excursions in the period">
              <DataTable
                columns={[
                  { key: 'trip_id', label: 'trip_id' },
                  { key: 'vehicle_id', label: 'vehicle_id' },
                  { key: 'trailer_id', label: 'trailer_id' },
                  { key: 'commodity', label: 'commodity' },
                  { key: 'peak_temp_f', label: 'peak_temp_f (°F)' },
                  { key: 'duration_min', label: 'duration_min (min)' },
                ]}
                rows={series.high_risk_trips}
              />
            </Panel>
          </div>
        )
      }}
    </DashboardShell>
  )
}
