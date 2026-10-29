import { Link } from 'react-router-dom'
import InfoTip from '../components/InfoTip'
import ThemeToggle from '../components/ThemeToggle'
import { DASHBOARDS, KPI_GUIDE } from '../dashboards'
import { KPIS, KPI_GROUPS, QUESTIONS } from '../kpis/definitions'

const BETTER_LABEL = { up: 'Higher is better', down: 'Lower is better' }

function Field({ term, children }) {
  return (
    <div>
      <dt className="font-semibold text-slate-600 dark:text-slate-400">{term}</dt>
      <dd className="text-slate-700 dark:text-slate-300">{children}</dd>
    </div>
  )
}

// One KPI: meaning, why (business question), action, catalog reference, and the dashboards that show it. Formula is in the info tooltip.
function GuideCard({ kpiId, decisions }) {
  const kpi = KPIS[kpiId]
  const dashboards = DASHBOARDS.filter((dashboard) => dashboard.kpiIds.includes(kpiId))
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900/60">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          {kpi.name} <span className="font-normal text-slate-400 dark:text-slate-600">#{kpiId}</span>
        </h3>
        <InfoTip label={`Formula of ${kpi.name}`}>
          <b>Formula</b>
          <br />
          {kpi.formula}
        </InfoTip>
      </div>
      <p className="text-xs text-slate-500">
        {kpi.unit} · {BETTER_LABEL[kpi.better] ?? 'Neutral'}
      </p>
      <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">{kpi.meaning}</p>
      <dl className="mt-3 space-y-2 text-xs">
        <Field term="Why we track it">
          {kpi.question}: {QUESTIONS[kpi.question]}
        </Field>
        <Field term="Business action">{kpi.action ?? decisions}</Field>
        <Field term="Reference">Notion_Data_Catalog.md › KPI {kpiId}</Field>
        <Field term="Shown on">
          {dashboards.length === 0
            ? 'Not on a dashboard yet'
            : dashboards.map((dashboard, index) => (
                <span key={dashboard.id}>
                  {index > 0 && ', '}
                  <Link to={dashboard.path} className="text-sky-700 hover:underline dark:text-sky-300">
                    {dashboard.title}
                  </Link>
                </span>
              ))}
        </Field>
      </dl>
    </article>
  )
}

export default function KpiGuidePage() {
  const kpiIds = Object.keys(KPIS).map(Number)
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{KPI_GUIDE.title}</h1>
          <p className="text-xs text-slate-500">What each KPI means, why we track it, and how it is calculated (hover the info icon).</p>
        </div>
        <ThemeToggle />
      </header>
      {KPI_GROUPS.map((group) => (
        <section key={group.title}>
          <h2 className="mb-3 text-sm font-semibold text-slate-800 dark:text-slate-200">{group.title}</h2>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {kpiIds
              .filter((kpiId) => kpiId >= group.from && kpiId <= group.to)
              .map((kpiId) => (
                <GuideCard key={kpiId} kpiId={kpiId} decisions={group.decisions} />
              ))}
          </div>
        </section>
      ))}
    </div>
  )
}
