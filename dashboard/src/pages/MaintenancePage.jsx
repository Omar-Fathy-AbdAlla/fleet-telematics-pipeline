import { BarChartView, LineChartView } from '../components/charts'
import DashboardShell from '../components/DashboardShell'
import DataTable from '../components/DataTable'
import { usd } from '../components/format'
import Panel from '../components/Panel'

export default function MaintenancePage() {
  return (
    <DashboardShell dashboardId="maintenance">
      {(series) => (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Monthly maintenance cost" subtitle="Labor + parts (USD)">
            <BarChartView
              data={series.cost_trend}
              xKey="month"
              bars={[{ key: 'labor_cost', label: 'labor_cost (USD)' }, { key: 'parts_cost', label: 'parts_cost (USD)' }]}
              stacked
            />
          </Panel>
          <Panel title="Maintenance mix" subtitle="Total cost by maintenance_type (USD): which categories drive cost">
            <BarChartView
              data={series.maintenance_mix}
              xKey="maintenance_type"
              bars={[{ key: 'total_cost', label: 'total_cost (USD)', color: '#a78bfa' }]}
              layout="vertical"
            />
          </Panel>
          <Panel title="Trucks with repeated orders" subtitle="Candidates for replacement or root-cause review">
            <DataTable
              columns={[
                { key: 'truck_id', label: 'truck_id' },
                { key: 'make', label: 'make' },
                { key: 'orders', label: 'orders (count)' },
                { key: 'total_cost', label: 'total_cost (USD)', format: usd },
                { key: 'downtime_hours', label: 'downtime_hours (h)' },
              ]}
              rows={series.repeat_trucks}
            />
          </Panel>
          <Panel
            title="Maintenance cost per km by model year"
            subtitle="USD per km, per truck model_year"
          >
            <LineChartView data={series.cost_by_model_year} xKey="model_year" lines={[{ key: 'kpi_44' }]} />
          </Panel>
        </div>
      )}
    </DashboardShell>
  )
}
