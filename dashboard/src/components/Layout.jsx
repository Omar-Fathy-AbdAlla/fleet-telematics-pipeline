import { NavLink, Outlet } from 'react-router-dom'
import { DASHBOARDS, KPI_GUIDE } from '../dashboards'

const navLinkClass = ({ isActive }) =>
  `whitespace-nowrap rounded-md px-3 py-2 text-sm ${
    isActive ? 'bg-sky-500/15 text-sky-700 dark:text-sky-300' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
  }`

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-800 md:flex-row dark:bg-slate-950 dark:text-slate-200">
      <aside className="w-full shrink-0 border-b border-slate-200 bg-white p-4 md:w-60 md:border-b-0 md:border-r dark:border-slate-800 dark:bg-slate-900/40">
        <div className="mb-5">
          <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">Fleet Data Platform</div>
        </div>
        <nav className="flex gap-1 overflow-x-auto md:flex-col">
          {DASHBOARDS.map((dashboard) => (
            <NavLink key={dashboard.id} to={dashboard.path} end className={navLinkClass}>
              {dashboard.title}
            </NavLink>
          ))}
        </nav>
        <nav className="mt-4 border-t border-slate-200 pt-4 dark:border-slate-800 md:flex md:flex-col">
          {/* Opens in a new browser tab so the viewer keeps the dashboard they are reading. */}
          <NavLink to={KPI_GUIDE.path} target="_blank" rel="noopener noreferrer" className={navLinkClass}>
            {KPI_GUIDE.title}
          </NavLink>
        </nav>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  )
}
