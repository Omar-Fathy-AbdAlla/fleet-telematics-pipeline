-- KPI 7 Dock Time (min): average detention_minutes of pickup and delivery events (loading / unloading time).
-- Period date: ACTUAL_DATE.
SELECT
    IFF(actual_date >= %(current_start)s, 'value', 'previous')   AS period,
    AVG(detention_minutes)                                       AS kpi_value
FROM fct_delivery_events
WHERE actual_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
