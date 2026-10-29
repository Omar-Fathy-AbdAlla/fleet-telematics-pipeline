import DashboardShell from '../components/DashboardShell'

// KPI cards only: the catalog's platform charts (pipeline runs, credits, S3 row counts) have no data source.
export default function PlatformPage() {
  return <DashboardShell dashboardId="platform" />
}
