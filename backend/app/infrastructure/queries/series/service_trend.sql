-- Chart service_trend (Executive): weekly KPI 1 On-Time Delivery Rate (pct), 12 weeks up to current_end.
SELECT
    DATE_TRUNC('week', actual_date)                    AS week_start,
    COUNT_IF(on_time_flag = 'TRUE') / COUNT(*) * 100   AS kpi_1
FROM fct_delivery_events
WHERE event_type = 'DELIVERY'
  AND actual_date BETWEEN DATEADD('week', -11, DATE_TRUNC('week', %(current_end)s::DATE)) AND %(current_end)s
GROUP BY week_start
ORDER BY week_start
