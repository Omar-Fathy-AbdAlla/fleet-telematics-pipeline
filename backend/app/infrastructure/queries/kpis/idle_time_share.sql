-- KPI 24 Idle Time Share (pct): SUM(idle_time_hours) / SUM(actual_duration_hours) x 100 over trips. Period date: ARRIVAL_TS date (day the trip finished).
SELECT
    IFF(arrival_ts::DATE >= %(current_start)s, 'value', 'previous')     AS period,
    SUM(idle_time_hours) / SUM(actual_duration_hours) * 100      AS kpi_value
FROM fct_trips
WHERE arrival_ts::DATE BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
