import { BarChartView, LineChartView } from '../components/charts'
import DashboardShell from '../components/DashboardShell'
import DataTable from '../components/DataTable'
import { lane, usd, usdCents } from '../components/format'
import Panel from '../components/Panel'

const WORST_ROUTES = 12

export default function FuelPage() {
  return (
    <DashboardShell dashboardId="fuel">
      {(series) => (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Weekly fuel spend" subtitle="Sum of fuel_purchases.total_cost per week (USD). Purchased, not burned.">
            <LineChartView data={series.fuel_spend_trend} xKey="week_start" lines={[{ key: 'total_cost', label: 'total_cost (USD)' }]} />
          </Panel>
          <Panel title="Diesel price by state vs national reference" subtitle="USD per liter. Compare within a state before flagging (state offsets exist).">
            <BarChartView
              data={series.price_by_state}
              xKey="location_state"
              bars={[
                { key: 'price_per_liter', label: 'price_per_liter (USD/L)' },
                { key: 'reference_price_per_liter', label: 'national reference (USD/L)', color: '#64748b' },
              ]}
            />
          </Panel>
          <Panel
            title={`Least fuel-efficient routes (worst ${WORST_ROUTES})`}
            subtitle="Fuel efficiency per route (handbook requirement). Expected fleet range 30-41 L/100km; higher = worse."
          >
            <BarChartView
              data={series.fuel_efficiency_by_route?.slice(0, WORST_ROUTES).map((row) => ({ ...row, lane: lane(row) }))}
              xKey="lane"
              bars={[{ key: 'kpi_21', color: '#fbbf24' }]}
              layout="vertical"
              height={340}
            />
          </Panel>
          <Panel title="Least fuel-efficient trucks" subtitle="Compare with similar trucks before acting">
            <DataTable columns={[{ key: 'truck_id', label: 'truck_id' }, { key: 'make', label: 'make' }, { key: 'kpi_21' }]} rows={series.fuel_efficiency_by_truck} />
          </Panel>
          <Panel className="lg:col-span-2" title="Fuel efficiency and cost per route (all lanes)">
            <div className="max-h-80 overflow-y-auto">
              <DataTable
                columns={[
                  { key: 'route_id', label: 'route_id' },
                  { key: 'lane', label: 'lane', format: (_, row) => lane(row) },
                  { key: 'kpi_21' },
                  { key: 'kpi_20', format: usdCents },
                ]}
                rows={series.fuel_efficiency_by_route}
              />
            </div>
          </Panel>
          <Panel className="lg:col-span-2" title="Fuel purchase outliers" subtitle="Highest price paid vs the national reference">
            <DataTable
              columns={[
                { key: 'fuel_purchase_id', label: 'fuel_purchase_id' },
                { key: 'truck_id', label: 'truck_id' },
                { key: 'location_state', label: 'location_state' },
                { key: 'liters', label: 'liters (L)' },
                { key: 'price_per_liter', label: 'price_per_liter (USD/L)', format: usdCents },
                { key: 'total_cost', label: 'total_cost (USD)', format: usd },
                { key: 'kpi_22' },
              ]}
              rows={series.purchase_outliers}
            />
          </Panel>
        </div>
      )}
    </DashboardShell>
  )
}
