// Shown instead of a chart or table when its series is null (not in the warehouse, e.g. live stream data) or empty.
export default function NoData() {
  return <p className="py-8 text-center text-xs text-slate-500">No data</p>
}
