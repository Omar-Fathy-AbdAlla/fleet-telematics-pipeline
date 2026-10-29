import { BarChartView } from '../components/charts'
import DashboardShell from '../components/DashboardShell'
import DataTable from '../components/DataTable'
import { usd } from '../components/format'
import Panel from '../components/Panel'

export default function SafetyPage() {
  return (
    <DashboardShell dashboardId="safety">
      {(series) => (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel
            className="lg:col-span-2"
            title="Driver safety & idling scorecard"
            subtitle="Handbook requirement. Drivers with the most incidents in the period."
          >
            <DataTable
              columns={[
                { key: 'driver_id', label: 'driver_id' },
                { key: 'driver', label: 'driver', format: (_, row) => `${row.first_name} ${row.last_name}` },
                { key: 'distance_km', label: 'distance_km (km)' },
                { key: 'kpi_24' },
                { key: 'incidents', label: 'incidents (count)' },
              ]}
              rows={series.driver_scorecard}
            />
          </Panel>
          <Panel title="Where truck time goes" subtitle="Share of total fleet hours (%). Long waits between loads are by design.">
            <BarChartView data={series.time_in_state} xKey="state" bars={[{ key: 'share_pct', label: 'share of time (%)' }]} layout="vertical" />
          </Panel>
          <Panel title="Incidents by type" subtitle="Count and total claim cost in the period">
            <DataTable
              columns={[
                { key: 'incident_type', label: 'incident_type' },
                { key: 'incidents', label: 'incidents (count)' },
                { key: 'claim_amount', label: 'claim_amount (USD)', format: usd },
              ]}
              rows={series.incidents_by_type}
            />
          </Panel>
        </div>
      )}
    </DashboardShell>
  )
}
