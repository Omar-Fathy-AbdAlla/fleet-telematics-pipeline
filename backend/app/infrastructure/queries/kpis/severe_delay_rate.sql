-- KPI 5 Severe Delay Rate (pct): delivery events with delay_minutes > 120 / all delivery events x 100.
-- 120 min is an assumption (catalog: the team picks the threshold). Period date: ACTUAL_DATE.
SELECT
    IFF(actual_date >= %(current_start)s, 'value', 'previous')   AS period,
    COUNT_IF(delay_minutes > 120) / COUNT(*) * 100               AS kpi_value
FROM fct_delivery_events
WHERE event_type = 'DELIVERY'
  AND actual_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
