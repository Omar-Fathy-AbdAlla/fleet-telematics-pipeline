// Small display formatters (table cells, page header).
export const usd = (value) =>
  value == null ? '-' : value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

export const usdCents = (value) =>
  value == null ? '-' : value.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })

export const yesNo = (value) => (value == null ? 'missing' : value ? 'yes' : 'no')

// Data times are UTC (event_ts, as_of, alerts); every time is shown in Cairo time (summer time included).
const CAIRO = { timeZone: 'Africa/Cairo', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }

// ISO timestamp -> "29 Oct 2026, 13:54:07"
export const dateTime = (iso) =>
  iso ? new Date(iso).toLocaleString('en-GB', { ...CAIRO, second: '2-digit', day: 'numeric', month: 'short', year: 'numeric' }) : '-'

// ISO timestamp -> "13:54"
export const hhmm = (iso) => (iso ? new Date(iso).toLocaleTimeString('en-GB', CAIRO) : '-')

export const lane =(row) => `${row.origin_city} → ${row.destination_city}`
