-- KPI 2 On-Time Pickup Rate (pct): pickup events with on_time_flag TRUE / all pickup events x 100.
-- on_time_flag already includes the 15-min grace period. Period date: ACTUAL_DATE.
SELECT
    IFF(actual_date >= %(current_start)s, 'value', 'previous')   AS period,
    COUNT_IF(on_time_flag = 'TRUE') / COUNT(*) * 100             AS kpi_value
FROM fct_delivery_events
WHERE event_type = 'PICKUP'
  AND actual_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
