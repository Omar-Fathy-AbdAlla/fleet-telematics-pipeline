import { LineChartView } from '../components/charts'
import DashboardShell from '../components/DashboardShell'
import Panel from '../components/Panel'

export default function ExecutivePage() {
  return (
    <DashboardShell dashboardId="executive">
      {(series) => (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Service quality trend" subtitle="Weekly on-time delivery (%)">
            <LineChartView data={series.service_trend} xKey="week_start" lines={[{ key: 'kpi_1' }]} />
          </Panel>
          <Panel
            title="Unit economics trend"
            subtitle="Revenue vs fuel cost per km (USD/km). The gap is what is left for driver pay, maintenance and profit."
          >
            <LineChartView data={series.unit_economics_trend} xKey="week_start" lines={[{ key: 'kpi_26' }, { key: 'kpi_20' }]} />
          </Panel>
        </div>
      )}
    </DashboardShell>
  )
}
