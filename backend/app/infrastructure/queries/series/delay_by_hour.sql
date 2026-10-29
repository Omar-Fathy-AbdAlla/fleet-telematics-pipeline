-- Chart delay_by_hour (Delivery): KPI 3 Average Delivery Delay (min, late deliveries only) per scheduled hour
-- (Cairo time; scheduled_datetime is UTC), current period. Same rule as kpis/average_delivery_delay.sql.
SELECT
    TO_CHAR(CONVERT_TIMEZONE('UTC', 'Africa/Cairo', scheduled_datetime), 'HH24') || ':00'   AS hour,
    AVG(delay_minutes)                             AS kpi_3
FROM fct_delivery_events
WHERE event_type = 'DELIVERY'
  AND delay_minutes > 0
  AND actual_date BETWEEN %(current_start)s AND %(current_end)s
GROUP BY hour
ORDER BY hour
