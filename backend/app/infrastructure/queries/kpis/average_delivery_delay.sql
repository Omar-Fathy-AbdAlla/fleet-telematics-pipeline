-- KPI 3 Average Delivery Delay (min): average delay_minutes of late deliveries only (delay_minutes > 0).
-- Early deliveries (negative delay) are excluded so they do not cancel out late ones. Period date: ACTUAL_DATE.
SELECT
    IFF(actual_date >= %(current_start)s, 'value', 'previous')   AS period,
    AVG(delay_minutes)                                           AS kpi_value
FROM fct_delivery_events
WHERE event_type = 'DELIVERY'
  AND delay_minutes > 0
  AND actual_date BETWEEN %(previous_start)s AND %(current_end)s
GROUP BY period
